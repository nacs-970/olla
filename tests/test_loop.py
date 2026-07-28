"""Tests for olla.loop."""

from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    ("limit", "expected_head", "expected_tail"),
    [
        (5, "ab", "fgh"),
        (1, "", "h"),
        (0, "", ""),
    ],
)
def test_truncate_output_respects_small_and_odd_limits(
    limit, expected_head, expected_tail
):
    text = "abcdefgh"

    assert truncate_output(text, limit=limit) == (
        f"{expected_head}\n[...truncated {len(text) - limit} chars...]\n"
        f"{expected_tail}"
    )


def test_truncate_output_rejects_negative_limit():
    with pytest.raises(ValueError, match="limit must be non-negative"):
        truncate_output("text", limit=-1)


def test_call_model(mocker):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<final>42</final>"}}

    messages = [{"role": "user", "content": "hi"}]
    result = call_model("test-model", messages)

    assert result == "<final>42</final>"
    mock_chat.assert_called_once_with(
        model="test-model",
        messages=messages,
        options={"stop": ["</args>"], "num_ctx": 8192},
        think=False,
    )


def test_run_loop_remember_preserves_observation_substring(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {
            "message": {
                "content": (
                    "<tool>remember</tool><args>note\n"
                    "before Observation: after</args>"
                )
            }
        },
        {"message": {"content": "<tool>recall</tool><args>note</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]

    run_loop(
        task="remember a value containing protocol-like text",
        model="test-model",
        max_steps=3,
        system_prompt="sys",
    )

    assert "before Observation: after" in capsys.readouterr().out


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
        {"message": {"content": "<tool>browse</tool><args>https://example.com</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="browse a site", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "unknown tool 'browse'" in captured.out
    mock_run_shell.assert_not_called()

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: unknown tool 'browse'"


def test_run_loop_malformed_args_recovers(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": '<tool>shell</tool><args>echo "unterminated</args>'}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="say hi", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "could not parse shell command" in captured.out
    assert "done" in captured.out
    mock_run_shell.assert_not_called()

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert "could not parse shell command" in obs_messages[0]["content"]


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


def test_run_loop_read_file_dispatch_no_prompt(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/some/path</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/some/path", "content": "hello from file\n"}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="read a file", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "hello from file" in captured.out
    mock_confirm.assert_not_called()
    mock_read_file.assert_called_once()


def test_run_loop_read_file_truncates_large_output(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/big</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/big", "content": "x" * 5000}

    run_loop(task="read a big file", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "[...truncated" in captured.out


def test_run_loop_read_file_error_observation(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/missing</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/missing", "error": "file not found: /missing"}

    run_loop(task="read a missing file", model="test-model", max_steps=15, system_prompt="sys")

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert "file not found: /missing" in obs_messages[0]["content"]


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


def test_run_loop_write_file_confirm_approved(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\nnew content\n</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_write_file.return_value = {"path": "/tmp/x.txt", "bytes_written": 12}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "done" in captured.out
    mock_confirm.assert_called_once()
    mock_write_file.assert_called_once()


def test_run_loop_write_file_shows_resolved_path(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\nnew content\n</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_write_file.return_value = {"path": "/tmp/x.txt", "bytes_written": 12}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys")

    resolved = str(Path("/tmp/x.txt").resolve())
    prompt_text = mock_confirm.call_args[0][0]
    assert resolved in prompt_text


def test_run_loop_write_file_confirm_declined(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\nnew content\n</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=False)

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys")

    mock_confirm.assert_called_once()
    mock_write_file.assert_not_called()
    assert mock_chat.call_count == 2

    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert obs_messages[0]["content"] == "Observation: declined by user"


def test_run_loop_write_file_yes_skips_prompt(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\nnew content\n</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_write_file.return_value = {"path": "/tmp/x.txt", "bytes_written": 12}
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    mock_confirm.assert_not_called()
    mock_write_file.assert_called_once()


def test_run_loop_write_file_no_newline_discloses_empty_write(mocker, capsys):
    # CR-03 regression: model emits write_file with only a path (no newline/content).
    # The confirm prompt must disclose the emptiness rather than silently asking
    # "Write to ...?" which would truncate the file to 0 bytes on approval.
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>/some/path.txt</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=False)

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys")

    # The Confirm prompt must NOT have been called (refusal happens before it)
    mock_confirm.assert_not_called()
    # write_file must never be called
    mock_write_file.assert_not_called()
    # The observation message must mention the refusal
    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert "refused" in obs_messages[0]["content"] or "no content" in obs_messages[0]["content"]


def test_run_loop_write_file_no_newline_with_yes_still_discloses_or_refuses(mocker, capsys):
    # CR-03 regression: --yes cannot meaningfully approve a no-content write.
    # The refusal must happen BEFORE the if-not-yes gate so --yes cannot bypass it.
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>/some/path.txt</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    mock_confirm.assert_not_called()
    mock_write_file.assert_not_called()
    call_args = mock_chat.call_args_list[1]
    messages = call_args.kwargs["messages"]
    obs_messages = [m for m in messages if m["role"] == "user" and m["content"].startswith("Observation:")]
    assert len(obs_messages) == 1
    assert "refused" in obs_messages[0]["content"] or "no content" in obs_messages[0]["content"]


def test_dry_run_write_file_no_newline_discloses_empty_write(mocker, capsys):
    # CR-03 regression: dry-run preview for a no-newline write_file must NOT print
    # the normal "would prompt for confirmation" text — it must disclose the refusal.
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>write_file</tool><args>/some/path.txt</args>"}}

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    # Must NOT say normal confirmation text
    assert "would prompt for confirmation" not in captured.out
    # Must indicate the write is refused / no content provided
    assert "refused" in captured.out or "no content" in captured.out


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


def test_run_loop_env_unset_sudo_with_yes_still_blocks(mocker, capsys):
    # CR-01 regression: `env -u FOO sudo rm -rf /` must BLOCK even with --yes.
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>env -u FOO sudo rm -rf /</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="delete everything", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    captured = capsys.readouterr()
    assert "blocked by safety policy:" in captured.out
    assert "sudo" in captured.out
    mock_run_shell.assert_not_called()


def test_run_loop_find_multi_exec_sudo_with_yes_still_blocks(mocker, capsys):
    # CR-01 regression: a find call chaining multiple -exec clauses, where a
    # later clause wraps `sudo rm -rf /`, must BLOCK even with --yes.
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>shell</tool><args>find . -exec true ; -exec sudo rm -rf / ;</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="clean up files", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    captured = capsys.readouterr()
    assert "blocked by safety policy:" in captured.out
    assert "sudo" in captured.out
    mock_run_shell.assert_not_called()


# CR-01 (round 2): bash -c "sudo rm -rf /" must BLOCK even with --yes (02-VERIFICATION.md gap 1/3).
def test_run_loop_bash_dash_c_sudo_with_yes_still_blocks(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": '<tool>shell</tool><args>bash -c "sudo rm -rf /"</args>'}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="delete everything", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    captured = capsys.readouterr()
    assert "blocked by safety policy:" in captured.out
    assert "sudo" in captured.out
    mock_run_shell.assert_not_called()


# CR-01 (round 3): bash -lc "sudo rm -rf /" (combined short flag) must BLOCK
# even with --yes (02-VERIFICATION.md round 3 gap).
def test_run_loop_bash_dash_lc_sudo_with_yes_still_blocks(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": '<tool>shell</tool><args>bash -lc "sudo rm -rf /"</args>'}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")

    run_loop(task="delete everything", model="test-model", max_steps=15, system_prompt="sys", yes=True)

    captured = capsys.readouterr()
    assert "blocked by safety policy:" in captured.out
    assert "sudo" in captured.out
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


def test_dry_run_previews_read_file(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>read_file</tool><args>/some/path</args>"}}
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="read a file", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    assert "Step 1 would read: /some/path" in captured.out
    assert mock_chat.call_count == 1
    mock_run_shell.assert_not_called()
    mock_confirm.assert_not_called()


def test_dry_run_previews_write_file(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\ncontent\n</args>"}}
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(task="write a file", model="test-model", max_steps=15, system_prompt="sys", dry_run=True)

    captured = capsys.readouterr()
    resolved = str(Path("/tmp/x.txt").resolve())
    assert "would write" in captured.out
    assert resolved in captured.out
    assert "would prompt for confirmation" in captured.out
    assert mock_chat.call_count == 1
    mock_confirm.assert_not_called()
    mock_write_file.assert_not_called()


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
    assert "could not parse shell command" in captured.out
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


def test_run_loop_repetition_guard_covers_read_file(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/same/path</args>"}},
        {"message": {"content": "<tool>read_file</tool><args>/same/path</args>"}},
        {"message": {"content": "<tool>read_file</tool><args>/same/path</args>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/same/path", "content": "hello\n"}

    run_loop(task="read same file repeatedly", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same read_file call repeated 3x — model likely stuck" in captured.out
    assert mock_read_file.call_count == 2
    assert mock_chat.call_count == 3


def test_run_loop_repetition_guard_covers_write_file(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\nsame content\n</args>"}},
        {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\nsame content\n</args>"}},
        {"message": {"content": "<tool>write_file</tool><args>/tmp/x.txt\nsame content\n</args>"}},
    ]
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_write_file.return_value = {"path": "/tmp/x.txt", "bytes_written": 13}
    mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(task="write same file repeatedly", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "olla stopped: same write_file call repeated 3x — model likely stuck" in captured.out
    assert mock_write_file.call_count <= 2
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


def test_run_loop_read_then_write_end_to_end(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>read_file</tool><args>/tmp/in.txt</args>"}},
        {"message": {"content": "<tool>write_file</tool><args>/tmp/out.txt\nmodified content\n</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_read_file = mocker.patch("olla.loop.read_file")
    mock_read_file.return_value = {"path": "/tmp/in.txt", "content": "original content\n"}
    mock_write_file = mocker.patch("olla.loop.write_file")
    mock_write_file.return_value = {"path": "/tmp/out.txt", "bytes_written": 17}
    mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop(task="read a file and write a modified copy", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "done" in captured.out
    mock_read_file.assert_called_once()
    mock_write_file.assert_called_once()
    assert mock_chat.call_count == 3


def test_run_loop_same_target_edit_preserves_unrequested_bytes(
    tmp_path, mocker, capsys
):
    target = tmp_path / "settings.ini"
    original = "# prefix\nname=olla\nmode=slow\n\nkeep=this suffix\n"
    expected = "# prefix\nname=olla\nmode=fast\n\nkeep=this suffix\n"
    target.write_text(original, encoding="utf-8")
    mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>read_file</tool><args>{target}</args>",
            f"<tool>write_file</tool><args>{target}\n{expected}</args>",
            "<final>done</final>",
        ],
    )
    mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop("change mode to fast", "model", 3, "sys")

    output = capsys.readouterr().out
    assert target.read_bytes() == expected.encode("utf-8")
    assert "Overwrite existing file" in output
    assert "--- current:" in output
    assert "+++ proposed:" in output
    assert "-mode=slow" in output
    assert "+mode=fast" in output


@pytest.mark.parametrize("yes", [False, True])
def test_run_loop_existing_file_requires_complete_same_run_read(
    tmp_path, mocker, yes
):
    target = tmp_path / "existing.txt"
    target.write_text("original\n", encoding="utf-8")
    mock_model = mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>write_file</tool><args>{target}\nunrelated\n</args>",
            "<final>done</final>",
        ],
    )
    mock_write = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop("edit the file", "model", 2, "sys", yes=yes)

    mock_confirm.assert_not_called()
    mock_write.assert_not_called()
    assert target.read_text(encoding="utf-8") == "original\n"
    messages = mock_model.call_args_list[1].args[1]
    observations = [
        message["content"]
        for message in messages
        if message["role"] == "user"
        and message["content"].startswith("Observation:")
    ]
    assert any(str(target.resolve()) in message for message in observations)
    assert any("read_file" in message and "before overwrite" in message for message in observations)


def test_run_loop_resolved_alias_read_authorizes_previewed_overwrite(
    tmp_path, mocker, capsys
):
    target = tmp_path / "existing.txt"
    target.write_text("name: old\nkeep: yes\n", encoding="utf-8")
    read_alias = target.parent / "." / target.name
    write_alias = target.parent / "nested" / ".." / target.name
    mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>read_file</tool><args>{read_alias}</args>",
            (
                f"<tool>write_file</tool><args>{write_alias}\n"
                "name: new\nkeep: yes\n</args>"
            ),
            "<final>done</final>",
        ],
    )
    mock_write = mocker.patch(
        "olla.loop.write_file",
        return_value={"path": str(target), "bytes_written": 20},
    )
    mock_confirm = mocker.patch("olla.loop.Confirm.ask", return_value=True)

    run_loop("edit the name", "model", 3, "sys")

    output = capsys.readouterr().out
    assert "Overwrite existing file" in output
    assert str(target.resolve()) in output
    assert "Current bytes:" in output
    assert "Proposed bytes:" in output
    assert "--- current:" in output
    assert "+++ proposed:" in output
    assert "-name: old" in output
    assert "+name: new" in output
    assert "Overwrite existing file" in mock_confirm.call_args.args[0]
    assert str(target.resolve()) in mock_confirm.call_args.args[0]
    mock_write.assert_called_once_with(
        str(target.resolve()), "name: new\nkeep: yes\n"
    )


def test_run_loop_failed_read_does_not_authorize_existing_overwrite(
    tmp_path, mocker
):
    target = tmp_path / "existing.txt"
    target.write_text("original\n", encoding="utf-8")
    mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>read_file</tool><args>{target}</args>",
            f"<tool>write_file</tool><args>{target}\nreplacement\n</args>",
            "<final>done</final>",
        ],
    )
    mocker.patch(
        "olla.loop.read_file",
        return_value={"path": str(target), "error": "permission denied"},
    )
    mock_write = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop("edit the file", "model", 3, "sys")

    mock_confirm.assert_not_called()
    mock_write.assert_not_called()
    assert target.read_text(encoding="utf-8") == "original\n"


def test_run_loop_truncated_read_does_not_authorize_existing_overwrite(
    tmp_path, mocker
):
    target = tmp_path / "existing.txt"
    original = "x" * (MAX_OBSERVATION_CHARS + 1)
    target.write_text(original, encoding="utf-8")
    mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>read_file</tool><args>{target}</args>",
            f"<tool>write_file</tool><args>{target}\nreplacement\n</args>",
            "<final>done</final>",
        ],
    )
    mock_write = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop("edit the file", "model", 3, "sys")

    mock_confirm.assert_not_called()
    mock_write.assert_not_called()
    assert target.read_text(encoding="utf-8") == original


def test_run_loop_stale_snapshot_is_refused_before_confirmation(
    tmp_path, mocker
):
    target = tmp_path / "existing.txt"
    target.write_text("original\n", encoding="utf-8")
    responses = iter(
        [
            f"<tool>read_file</tool><args>{target}</args>",
            f"<tool>write_file</tool><args>{target}\nreplacement\n</args>",
            "<final>done</final>",
        ]
    )
    call_count = 0

    def fake_model(*_args):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            target.write_text("changed externally\n", encoding="utf-8")
        return next(responses)

    mock_model = mocker.patch("olla.loop.call_model", side_effect=fake_model)
    mock_write = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop("edit the file", "model", 3, "sys")

    mock_confirm.assert_not_called()
    mock_write.assert_not_called()
    assert target.read_text(encoding="utf-8") == "changed externally\n"
    messages = mock_model.call_args_list[2].args[1]
    assert any(
        "changed" in message["content"] and "read_file" in message["content"]
        for message in messages
        if message["role"] == "user"
    )


def test_run_loop_post_confirmation_change_is_refused(tmp_path, mocker):
    target = tmp_path / "existing.txt"
    target.write_text("original\n", encoding="utf-8")
    mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>read_file</tool><args>{target}</args>",
            f"<tool>write_file</tool><args>{target}\nreplacement\n</args>",
            "<final>done</final>",
        ],
    )
    mock_write = mocker.patch("olla.loop.write_file")

    def change_then_approve(*_args, **_kwargs):
        target.write_text("changed during confirmation\n", encoding="utf-8")
        return True

    mocker.patch("olla.loop.Confirm.ask", side_effect=change_then_approve)

    run_loop("edit the file", "model", 3, "sys")

    mock_write.assert_not_called()
    assert target.read_text(encoding="utf-8") == "changed during confirmation\n"


def test_run_loop_new_target_appearing_during_confirmation_is_preserved(
    tmp_path, mocker
):
    target = tmp_path / "new.txt"
    mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>write_file</tool><args>{target}\nmodel content\n</args>",
            "<final>done</final>",
        ],
    )
    mock_write = mocker.patch("olla.loop.write_file")

    def create_then_approve(*_args, **_kwargs):
        target.write_text("created externally\n", encoding="utf-8")
        return True

    mocker.patch("olla.loop.Confirm.ask", side_effect=create_then_approve)

    run_loop("create the file", "model", 2, "sys")

    mock_write.assert_not_called()
    assert target.read_text(encoding="utf-8") == "created externally\n"


def test_run_loop_creates_absent_target_with_bounded_preview(
    tmp_path, mocker, capsys
):
    target = tmp_path / "new.txt"
    content = "start\n" + ("x" * (MAX_OBSERVATION_CHARS + 100)) + "\nend\n"
    mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            f"<tool>write_file</tool><args>{target}\n{content}</args>",
            "<final>done</final>",
        ],
    )
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop("create the file", "model", 2, "sys", yes=True)

    output = capsys.readouterr().out
    assert "Create new file" in output
    assert str(target.resolve()) in output
    assert f"Proposed bytes: {len(content.encode('utf-8'))}" in output
    assert "[...truncated" in output
    assert target.read_text(encoding="utf-8") == content
    mock_confirm.assert_not_called()


@pytest.mark.parametrize(
    "tool_call",
    [
        "<tool>read_file</tool><args>bad\x00path</args>",
        "<tool>write_file</tool><args>bad\x00path\ncontent</args>",
    ],
)
def test_run_loop_malformed_file_path_becomes_observation(mocker, tool_call):
    mock_model = mocker.patch(
        "olla.loop.call_model", side_effect=[tool_call, "<final>done</final>"]
    )
    mock_read = mocker.patch("olla.loop.read_file")
    mock_write = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop("use a malformed path", "model", 2, "sys")

    mock_read.assert_not_called()
    mock_write.assert_not_called()
    mock_confirm.assert_not_called()
    messages = mock_model.call_args_list[1].args[1]
    assert any(
        "could not resolve file path" in message["content"]
        for message in messages
        if message["role"] == "user"
    )


@pytest.mark.parametrize(
    "tool_call",
    [
        "<tool>read_file</tool><args>bad\x00path</args>",
        "<tool>write_file</tool><args>bad\x00path\ncontent</args>",
    ],
)
def test_dry_run_malformed_file_path_prints_error_without_side_effects(
    mocker, capsys, tool_call
):
    mocker.patch("olla.loop.call_model", return_value=tool_call)
    mock_read = mocker.patch("olla.loop.read_file")
    mock_write = mocker.patch("olla.loop.write_file")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop("preview a malformed path", "model", 1, "sys", dry_run=True)

    assert "could not resolve file path" in capsys.readouterr().out
    mock_read.assert_not_called()
    mock_write.assert_not_called()
    mock_confirm.assert_not_called()


def test_run_loop_runtime_path_resolution_failure_is_recoverable(mocker):
    mock_model = mocker.patch(
        "olla.loop.call_model",
        side_effect=[
            "<tool>read_file</tool><args>loop</args>",
            "<final>done</final>",
        ],
    )
    mocker.patch("olla.loop.Path.resolve", side_effect=RuntimeError("symlink loop"))
    mock_read = mocker.patch("olla.loop.read_file")

    run_loop("read a looping path", "model", 2, "sys")

    mock_read.assert_not_called()
    messages = mock_model.call_args_list[1].args[1]
    assert any(
        "could not resolve file path" in message["content"]
        for message in messages
        if message["role"] == "user"
    )


@pytest.mark.parametrize("yes", [False, True])
def test_run_loop_remember_recall_then_final(mocker, capsys, yes):
    responses = iter(
        [
            {"message": {"content": "<tool>remember</tool><args>meeting_time\n3pm</args>"}},
            {"message": {"content": "<tool>recall</tool><args>meeting_time</args>"}},
            {"message": {"content": "<final>The meeting is at 3pm.</final>"}},
        ]
    )
    messages_by_call = []

    def fake_chat(**kwargs):
        messages_by_call.append([message.copy() for message in kwargs["messages"]])
        return next(responses)

    mock_chat = mocker.patch("olla.loop.ollama.chat", side_effect=fake_chat)
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(
        task="remember and report the meeting time",
        model="test-model",
        max_steps=15,
        system_prompt="sys",
        yes=yes,
    )

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "Step 1: remembering meeting_time...",
        "remembered: meeting_time",
        "Step 2: recalling meeting_time...",
        "3pm",
        "The meeting is at 3pm.",
    ]
    mock_confirm.assert_not_called()
    assert mock_chat.call_count == 3

    second_observations = [
        message["content"]
        for message in messages_by_call[1]
        if message["role"] == "user" and message["content"].startswith("Observation:")
    ]
    assert second_observations == ["Observation: remembered: meeting_time"]

    third_observations = [
        message["content"]
        for message in messages_by_call[2]
        if message["role"] == "user" and message["content"].startswith("Observation:")
    ]
    assert third_observations == [
        "Observation: remembered: meeting_time",
        "Observation: 3pm",
    ]


def test_run_loop_scratchpad_isolation_between_invocations(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>remember</tool><args>meeting_time\n3pm</args>"}},
        {"message": {"content": "<final>first run done</final>"}},
        {"message": {"content": "<tool>recall</tool><args>meeting_time</args>"}},
        {"message": {"content": "<final>second run done</final>"}},
    ]
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")

    run_loop(
        task="remember the meeting time",
        model="test-model",
        max_steps=15,
        system_prompt="sys",
    )
    run_loop(
        task="recall the meeting time",
        model="test-model",
        max_steps=15,
        system_prompt="sys",
    )

    captured = capsys.readouterr()
    assert "remembered: meeting_time" in captured.out
    assert "memory not found: meeting_time" in captured.out
    mock_confirm.assert_not_called()


@pytest.mark.parametrize("yes", [False, True])
def test_run_loop_memory_never_confirms_or_checks(mocker, capsys, yes):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>remember</tool><args>secret\nTOP_SECRET</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")
    mock_check = mocker.patch("olla.loop.check")

    run_loop(
        task="remember privately",
        model="test-model",
        max_steps=15,
        system_prompt="sys",
        yes=yes,
    )

    captured = capsys.readouterr()
    assert "Step 1: remembering secret..." in captured.out
    assert "remembered: secret" in captured.out
    assert "TOP_SECRET" not in captured.out
    mock_confirm.assert_not_called()
    mock_check.assert_not_called()


def test_run_loop_unclosed_memory_tool_does_not_disclose_value(mocker, capsys):
    messages_by_call = []
    responses = iter(
        [
            {"message": {"content": "<tool>remember<args>key\nTOP_SECRET</args>"}},
            {"message": {"content": "<final>done</final>"}},
        ]
    )

    def fake_chat(**kwargs):
        messages_by_call.append([message.copy() for message in kwargs["messages"]])
        return next(responses)

    mocker.patch("olla.loop.ollama.chat", side_effect=fake_chat)

    run_loop(
        task="remember privately",
        model="test-model",
        max_steps=2,
        system_prompt="sys",
    )

    assert "TOP_SECRET" not in capsys.readouterr().out
    observations = [
        message["content"]
        for message in messages_by_call[1]
        if message["role"] == "user"
        and message["content"].startswith("Observation:")
    ]
    assert observations == ["Observation: remembered: key"]


def test_dry_run_unclosed_memory_tool_does_not_disclose_value(mocker, capsys):
    mocker.patch(
        "olla.loop.ollama.chat",
        return_value={
            "message": {"content": "<tool>remember<args>key\nTOP_SECRET</args>"}
        },
    )

    run_loop(
        task="preview private memory",
        model="test-model",
        max_steps=1,
        system_prompt="sys",
        dry_run=True,
    )

    captured = capsys.readouterr().out
    assert captured == "Step 1 would remember: key (10 chars)\n"
    assert "TOP_SECRET" not in captured


@pytest.mark.parametrize(
    ("tool_content", "expected"),
    [
        (
            "<tool>remember</tool><args> note \nTOP_SECRET</args>",
            "Step 1 would remember: note (10 chars)",
        ),
        (
            "<tool>recall</tool><args> note </args>",
            "Step 1 would recall: note",
        ),
    ],
)
def test_dry_run_memory_preview_is_non_accessing(mocker, capsys, tool_content, expected):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": tool_content}}
    mock_remember = mocker.patch("olla.loop.Scratchpad.remember")
    mock_recall = mocker.patch("olla.loop.Scratchpad.recall")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")
    mock_check = mocker.patch("olla.loop.check")

    run_loop(
        task="preview memory",
        model="test-model",
        max_steps=15,
        system_prompt="sys",
        dry_run=True,
    )

    captured = capsys.readouterr()
    assert captured.out == f"{expected}\n"
    assert "TOP_SECRET" not in captured.out
    assert mock_chat.call_count == 1
    mock_remember.assert_not_called()
    mock_recall.assert_not_called()
    mock_confirm.assert_not_called()
    mock_check.assert_not_called()


@pytest.mark.parametrize(
    ("tool_content", "expected"),
    [
        (
            "<tool>remember</tool><args>\nvalue</args>",
            "invalid remember: key must not be empty",
        ),
        (
            "<tool>remember</tool><args>key</args>",
            "invalid remember: expected key on first line and value on remaining lines",
        ),
        (
            f"<tool>remember</tool><args>key\n{'x' * 2001}</args>",
            "memory value too large: 2001 characters; maximum is 2000",
        ),
        (
            "<tool>recall</tool><args>   </args>",
            "invalid recall: key must not be empty",
        ),
    ],
)
def test_dry_run_memory_errors_are_exact_and_non_accessing(
    mocker, capsys, tool_content, expected
):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.return_value = {"message": {"content": tool_content}}
    mock_remember = mocker.patch("olla.loop.Scratchpad.remember")
    mock_recall = mocker.patch("olla.loop.Scratchpad.recall")
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")
    mock_check = mocker.patch("olla.loop.check")

    run_loop(
        task="preview invalid memory",
        model="test-model",
        max_steps=15,
        system_prompt="sys",
        dry_run=True,
    )

    captured = capsys.readouterr()
    assert captured.out == f"{expected}\n"
    assert mock_chat.call_count == 1
    mock_remember.assert_not_called()
    mock_recall.assert_not_called()
    mock_confirm.assert_not_called()
    mock_check.assert_not_called()


@pytest.mark.parametrize(
    ("tool_content", "remember_result", "recall_result", "expected"),
    [
        (
            "<tool>remember</tool><args>key\nvalue</args>",
            {"content": "remembered: key"},
            None,
            "remembered: key",
        ),
        (
            "<tool>recall</tool><args>missing</args>",
            None,
            {"error": "memory not found: missing"},
            "memory not found: missing",
        ),
        (
            "<tool>recall</tool><args>empty</args>",
            None,
            {"content": "memory is empty: empty"},
            "memory is empty: empty",
        ),
        (
            "<tool>remember</tool><args>key\nvalue</args>",
            {"error": "memory key limit reached: maximum is 32"},
            None,
            "memory key limit reached: maximum is 32",
        ),
        (
            "<tool>remember</tool><args>key\nvalue</args>",
            {
                "error": (
                    "memory capacity exceeded: "
                    "write would use 16001 of 16000 characters"
                )
            },
            None,
            "memory capacity exceeded: write would use 16001 of 16000 characters",
        ),
        (
            "<tool>remember</tool><args>key</args>",
            None,
            None,
            "invalid remember: expected key on first line and value on remaining lines",
        ),
    ],
)
def test_run_loop_memory_results_match_observations(
    mocker,
    capsys,
    tool_content,
    remember_result,
    recall_result,
    expected,
):
    responses = iter(
        [
            {"message": {"content": tool_content}},
            {"message": {"content": "<final>done</final>"}},
        ]
    )
    messages_by_call = []

    def fake_chat(**kwargs):
        messages_by_call.append([message.copy() for message in kwargs["messages"]])
        return next(responses)

    mocker.patch("olla.loop.ollama.chat", side_effect=fake_chat)
    mock_remember = mocker.patch("olla.loop.Scratchpad.remember")
    mock_recall = mocker.patch("olla.loop.Scratchpad.recall")
    if remember_result is not None:
        mock_remember.return_value = remember_result
    if recall_result is not None:
        mock_recall.return_value = recall_result
    mock_confirm = mocker.patch("olla.loop.Confirm.ask")
    mock_check = mocker.patch("olla.loop.check")

    run_loop(task="exercise memory", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert expected in captured.out
    observations = [
        message["content"]
        for message in messages_by_call[1]
        if message["role"] == "user" and message["content"].startswith("Observation:")
    ]
    assert observations == [f"Observation: {expected}"]
    mock_confirm.assert_not_called()
    mock_check.assert_not_called()


@pytest.mark.parametrize(
    ("tool_calls", "method_name", "tool_name"),
    [
        (
            [
                "<tool>remember</tool><args> key \nvalue</args>",
                "<tool>remember</tool><args>key\nvalue</args>",
                "<tool>remember</tool><args> key\nvalue</args>",
            ],
            "remember",
            "remember",
        ),
        (
            [
                "<tool>recall</tool><args> key </args>",
                "<tool>recall</tool><args>key</args>",
                "<tool>recall</tool><args> key</args>",
            ],
            "recall",
            "recall",
        ),
    ],
)
def test_run_loop_memory_repetition_guard_uses_normalized_calls(
    mocker, capsys, tool_calls, method_name, tool_name
):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": tool_call}} for tool_call in tool_calls
    ]
    mock_remember = mocker.patch(
        "olla.loop.Scratchpad.remember", return_value={"content": "remembered: key"}
    )
    mock_recall = mocker.patch(
        "olla.loop.Scratchpad.recall", return_value={"content": "value"}
    )

    run_loop(task="repeat memory", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert f"olla stopped: same {tool_name} call repeated 3x — model likely stuck" in captured.out
    selected_method = mock_remember if method_name == "remember" else mock_recall
    assert selected_method.call_count == 2
    assert mock_chat.call_count == 3


def test_run_loop_different_memory_values_reset_repetition_guard(mocker, capsys):
    mock_chat = mocker.patch("olla.loop.ollama.chat")
    mock_chat.side_effect = [
        {"message": {"content": "<tool>remember</tool><args>key\none</args>"}},
        {"message": {"content": "<tool>remember</tool><args>key\none</args>"}},
        {"message": {"content": "<tool>remember</tool><args>key\ntwo</args>"}},
        {"message": {"content": "<tool>remember</tool><args>key\none</args>"}},
        {"message": {"content": "<tool>remember</tool><args>key\none</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_remember = mocker.patch(
        "olla.loop.Scratchpad.remember", return_value={"content": "remembered: key"}
    )

    run_loop(task="vary memory", model="test-model", max_steps=15, system_prompt="sys")

    captured = capsys.readouterr()
    assert "same remember call repeated 3x" not in captured.out
    assert "done" in captured.out
    assert mock_remember.call_count == 5
