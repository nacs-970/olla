"""Tests for olla.loop."""

from olla.loop import MAX_OBSERVATION_CHARS, call_model, run_loop, truncate_output
from olla.safety import check


def test_truncate_output_under_limit():
    text = "x" * MAX_OBSERVATION_CHARS
    assert truncate_output(text) == text


def test_truncate_output_over_limit():
    text = "x" * (MAX_OBSERVATION_CHARS + 500)
    result = truncate_output(text)
    assert text[:1000] in result
    assert text[-1000:] in result
    n = len(text) - MAX_OBSERVATION_CHARS
    assert f"[...truncated {n} chars...]" in result


def test_call_model(mocker):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<final>42</final>"}}

    messages = [{"role": "user", "content": "hi"}]
    result = call_model("test-model", messages)

    assert result == "<final>42</final>"
    mock_chat.assert_called_once_with(
        model="test-model",
        messages=messages,
        options={"stop": ["</args>", "Observation:"], "num_ctx": 8192},
        think=False,
    )


def test_run_loop_immediate_final(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<final>The answer is 42</final>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="what is the answer", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "The answer is 42" in captured.out
    mock_run_shell.assert_not_called()


def test_run_loop_tool_then_final(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>echo hi</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {
        "argv": ["echo", "hi"],
        "returncode": 0,
        "stdout": "hi\n",
        "stderr": "",
    }

    run_loop(task="say hi", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "Step 1: running ['echo', 'hi']..." in captured.out
    assert "hi\n" in captured.out
    assert "done" in captured.out

    # The same truncated string used for the printed preview must be the one
    # appended to the message history as the Observation.
    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: hi\n"


def test_run_loop_unknown_tool_returns_observation(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>foo.txt</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "unknown tool 'write_file'" in captured.out
    mock_run_shell.assert_not_called()

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: unknown tool 'write_file'"


def test_run_loop_malformed_args_recovers(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": '<tool>shell</tool><args>echo "unterminated</args>'}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="say hi", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "could not parse command" in captured.out
    assert "done" in captured.out
    mock_run_shell.assert_not_called()

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert "could not parse command" in obs_messages[0]["content"]


def test_run_loop_tool_result_real_no_output_success(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>cat /dev/null</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["cat", "/dev/null"], "returncode": 0, "stdout": "", "stderr": ""}

    run_loop(task="read a file", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "(no output)" in captured.out

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert obs_messages[0]["content"] == "Observation: (no output)"


def test_run_loop_truncates_none_response_in_history(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    long_text = "x" * (MAX_OBSERVATION_CHARS + 500)
    mock_chat.side_effect = [
        {"message": {"content": long_text}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mocker.patch("olla.loop.run_shell")

    run_loop(task="ponder", model="test-model", max_steps=15, system_prompt="sys")

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    assistant_messages = [m for m in messages if m["role"] == "assistant"]
    assert assistant_messages[0]["content"] == truncate_output(long_text)
    assert len(assistant_messages[0]["content"]) < len(long_text)


def test_run_loop_max_steps_no_final(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "I am thinking about it."}}
    mocker.patch("olla.loop.run_shell")

    run_loop(task="ponder", model="test-model", max_steps=2, system_prompt="sys")

    captured = capsys.readouterr()
    assert "Reached max steps (2) without a <final> answer." in captured.out
    assert mock_chat.call_count == 2

    # Verify a corrective re-prompt was appended after each `none`-type response
    # (one per step; `messages` is mutated in place, so by the end of the loop
    # both steps' corrective messages are present).
    last_call_messages = mock_chat.call_args_list[-1].kwargs["messages"]
    corrective = [
        m
        for m in last_call_messages
        if m["role"] == "user" and "No <tool> or <final> tag found" in m["content"]
    ]
    assert len(corrective) == 2


def test_run_loop_allow_tier_no_prompt(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["ls", "-la"], "returncode": 0, "stdout": "file1\n", "stderr": ""}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="list files", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "file1\n" in captured.out
    mock_confirm.assert_not_called()
    mock_run_shell.assert_called_once()


def test_run_loop_block_tier_never_calls_run_shell(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>rm -rf /</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="delete everything", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "blocked by safety policy:" in captured.out
    mock_run_shell.assert_not_called()

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert "blocked by safety policy:" in obs_messages[0]["content"]


def test_run_loop_confirm_approved_runs_shell(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["git", "status"], "returncode": 0, "stdout": "clean\n", "stderr": ""}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "clean\n" in captured.out
    mock_confirm.assert_called_once()
    mock_run_shell.assert_called_once()


def test_run_loop_confirm_declined_does_not_run_shell(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=False)

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys")

    mock_confirm.assert_called_once()
    mock_run_shell.assert_not_called()
    assert mock_chat.call_count == 2

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: declined by user"


def test_run_loop_confirm_tier_with_yes_skips_prompt(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["git", "status"], "returncode": 0, "stdout": "clean\n", "stderr": ""}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    mock_confirm.assert_not_called()
    mock_run_shell.assert_called_once()


def test_run_loop_confirm_eoferror_declines_safely(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>git status</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mocker.patch("olla.loop.Confirm.ask", side_effect=EOFError)

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys")

    mock_run_shell.assert_not_called()
    assert mock_chat.call_count == 2

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: declined by user"


def test_run_loop_block_tier_with_yes_still_blocks(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>rm -rf /</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="delete everything", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    captured = capsys.readouterr()
    assert "blocked by safety policy:" in captured.out
    mock_run_shell.assert_not_called()


def test_dry_run_final_response_prints_preview_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<final>42</final>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="what is the answer", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "Model would answer directly: 42" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_dry_run_none_response_prints_preview_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "I am thinking about it."}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="ponder", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "Model produced no valid <tool>/<final> tag: I am thinking about it." in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_dry_run_unknown_tool_prints_preview_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>browse</tool><args>https://example.com</args>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="browse the web", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "Model would call unknown tool 'browse'" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_dry_run_allow_tier_prints_preview_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="list files", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "Step 1 would run: ['ls', '-la'] — auto-approved (read-only allowlist)" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_dry_run_confirm_tier_prints_preview_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>shell</tool><args>git status</args>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="check status", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "Step 1 would run: ['git', 'status'] — would prompt for confirmation" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_dry_run_block_tier_prints_preview_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>shell</tool><args>rm -rf /</args>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="delete everything", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    expected_reason = check(["rm", "-rf", "/"], yes=False)["reason"]
    assert f"Step 1 would run: ['rm', '-rf', '/'] — BLOCKED: {expected_reason}" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_dry_run_malformed_args_prints_error_and_stops(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": '<tool>shell</tool><args>echo "unterminated</args>'}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="say hi", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "could not parse command" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_run_loop_repetition_guard_aborts_before_third_call(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["ls", "-la"], "returncode": 0, "stdout": "file1\n", "stderr": ""}

    run_loop(task="list files repeatedly", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same shell call repeated 3x — model likely stuck" in captured.out
    assert mock_run_shell.call_count == 2
    assert mock_chat.call_count == 3


def test_run_loop_two_repeats_then_different_proceeds_normally(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<tool>shell</tool><args>pwd</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.side_effect = [
        {"argv": ["ls", "-la"], "returncode": 0, "stdout": "file1\n", "stderr": ""},
        {"argv": ["ls", "-la"], "returncode": 0, "stdout": "file1\n", "stderr": ""},
        {"argv": ["pwd"], "returncode": 0, "stdout": "/home\n", "stderr": ""},
    ]

    run_loop(task="list then pwd", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same shell call repeated 3x" not in captured.out
    assert mock_run_shell.call_count == 3
    assert mock_chat.call_count == 4


def test_run_loop_block_interrupted_sequence_does_not_abort(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<tool>shell</tool><args>rm -rf /</args>"}},
        {"message": {"content": "<tool>shell</tool><args>ls -la</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["ls", "-la"], "returncode": 0, "stdout": "file1\n", "stderr": ""}

    run_loop(task="list, blocked, list", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same shell call repeated 3x" not in captured.out
    assert mock_run_shell.call_count == 2


def test_run_loop_repeated_block_triggers_repetition_guard(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>rm -rf /</args>"}},
        {"message": {"content": "<tool>shell</tool><args>rm -rf /</args>"}},
        {"message": {"content": "<tool>shell</tool><args>rm -rf /</args>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="delete everything repeatedly", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same shell call repeated 3x — model likely stuck" in captured.out
    mock_run_shell.assert_not_called()
    assert mock_chat.call_count == 3


def test_run_loop_max_steps_with_varied_shell_calls(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>ls</args>"}},
        {"message": {"content": "<tool>shell</tool><args>pwd</args>"}},
        {"message": {"content": "<tool>shell</tool><args>wc -l</args>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.side_effect = [
        {"argv": ["ls"], "returncode": 0, "stdout": "file1\n", "stderr": ""},
        {"argv": ["pwd"], "returncode": 0, "stdout": "/home\n", "stderr": ""},
        {"argv": ["wc", "-l"], "returncode": 0, "stdout": "3\n", "stderr": ""},
    ]

    run_loop(task="do something", model="m", max_steps=3, system_prompt="sys", dry_run=False)

    captured = capsys.readouterr()
    assert "Reached max steps (3) without a <final> answer." in captured.out
    assert "olla stopped: same shell call repeated 3x" not in captured.out
    assert mock_chat.call_count == 3
