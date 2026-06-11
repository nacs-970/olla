"""Tests for olla.loop."""

from olla.loop import MAX_OBSERVATION_CHARS, call_model, run_loop, truncate_output


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
        {"message": {"content": "<tool>shell</tool><args>touch foo</args>"}},
        {"message": {"content": "<final>done</final>"}},
    ]
    mock_run_shell = mocker.patch("olla.loop.run_shell")
    mock_run_shell.return_value = {"argv": ["touch", "foo"], "returncode": 0, "stdout": "", "stderr": ""}

    run_loop(task="touch a file", model="test-model", max_steps=15, system_prompt="sys")

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
