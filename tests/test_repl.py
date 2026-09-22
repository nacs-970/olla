"""Tests for olla.repl."""

from unittest.mock import MagicMock

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput

from olla.providers import ProviderError
from olla.repl import _build_key_bindings, main_loop


def test_main_loop_dispatches_two_turns_with_shared_session(mocker):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = ["do a", "do b", EOFError()]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    assert mock_run_loop.call_count == 2
    first_call, second_call = mock_run_loop.call_args_list
    assert first_call.kwargs["session"] is second_call.kwargs["session"]
    assert first_call.kwargs["model"] == "m"
    assert second_call.kwargs["model"] == "m"


def test_main_loop_provider_init_failure_prints_and_returns(mocker, capsys):
    mocker.patch("olla.repl.get_provider", side_effect=ProviderError("boom"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")

    main_loop(model="m", max_steps=5, system_prompt="sys")

    mock_run_loop.assert_not_called()
    assert "boom" in capsys.readouterr().out


def test_session_construction_uses_file_history_and_multiline(mocker):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [EOFError()]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    _, kwargs = mock_session_cls.call_args
    assert isinstance(kwargs["history"], FileHistory)
    assert kwargs["multiline"] is False
    assert isinstance(kwargs["key_bindings"], KeyBindings)


def test_newline_key_bindings_insert_without_submitting():
    """Both Alt+Enter and Ctrl+J are bound (Alt+Enter is often intercepted by
    the terminal emulator itself, e.g. for a fullscreen toggle, before it
    ever reaches the running program — Ctrl+J is a fallback that isn't)."""
    kb = _build_key_bindings()

    assert len(kb.bindings) == 2
    bound_keys = {binding.keys for binding in kb.bindings}
    assert bound_keys == {(Keys.Escape, Keys.ControlM), (Keys.ControlJ,)}

    for binding in kb.bindings:
        fake_event = MagicMock()
        binding.handler(fake_event)
        fake_event.current_buffer.insert_text.assert_called_once_with("\n")
        fake_event.current_buffer.validate_and_handle.assert_not_called()


def test_alt_enter_inserts_newline_via_real_pipe_input_prompt_session():
    with create_pipe_input() as pipe_input:
        session = PromptSession(
            input=pipe_input,
            output=DummyOutput(),
            key_bindings=_build_key_bindings(),
            multiline=False,
        )
        pipe_input.send_text("line1\x1b\rline2\r")

        result = session.prompt()

    assert result == "line1\nline2"


def test_ctrl_j_inserts_newline_via_real_pipe_input_prompt_session():
    with create_pipe_input() as pipe_input:
        session = PromptSession(
            input=pipe_input,
            output=DummyOutput(),
            key_bindings=_build_key_bindings(),
            multiline=False,
        )
        pipe_input.send_text("line1\x0aline2\r")

        result = session.prompt()

    assert result == "line1\nline2"


def test_exit_semantics_single_ctrl_c_continues(mocker):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        KeyboardInterrupt(),
        KeyboardInterrupt(),  # second interrupt, but past the double-tap threshold
        "do a",
        EOFError(),
    ]
    mocker.patch("olla.repl.time.monotonic", side_effect=[0.0, 10.0])

    main_loop(model="m", max_steps=5, system_prompt="sys")

    mock_run_loop.assert_called_once()


def test_exit_semantics_double_ctrl_c_exits(mocker):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        KeyboardInterrupt(),
        KeyboardInterrupt(),
    ]
    mocker.patch("olla.repl.time.monotonic", side_effect=[0.0, 0.5])

    main_loop(model="m", max_steps=5, system_prompt="sys")

    mock_run_loop.assert_not_called()


def test_main_loop_uses_raw_patch_stdout(mocker):
    """main_loop must open patch_stdout(raw=True). Without raw=True, prompt_toolkit's
    StdoutProxy routes prints through Vt100_Output.write(), which replaces every ESC
    byte with a literal '?' (see test_patch_stdout_raw_preserves_escape_codes below) —
    this is what turned the dimmed-thinking styling into visible '?[2m...?[0m' garbage
    in a live REPL terminal."""
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = ["do a", EOFError()]
    mock_patch_stdout = mocker.patch("olla.repl.patch_stdout")

    main_loop(model="m", max_steps=5, system_prompt="sys")

    mock_patch_stdout.assert_called_once_with(raw=True)


def test_patch_stdout_raw_preserves_escape_codes():
    """Regression for the bug test_main_loop_uses_raw_patch_stdout guards against:
    patch_stdout(raw=True) passes ESC bytes through untouched; patch_stdout(raw=False)
    (the default) strips them to '?' via Vt100_Output.write()."""
    from io import StringIO

    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.output.vt100 import Vt100_Output
    from prompt_toolkit.patch_stdout import patch_stdout

    dimmed = "\033[2mdim\033[0m"

    raw_buffer = StringIO()
    with create_app_session(output=Vt100_Output(raw_buffer, lambda: (24, 80))):
        with patch_stdout(raw=True):
            print(dimmed, end="", flush=True)
    assert dimmed in raw_buffer.getvalue()

    stripped_buffer = StringIO()
    with create_app_session(output=Vt100_Output(stripped_buffer, lambda: (24, 80))):
        with patch_stdout(raw=False):
            print(dimmed, end="", flush=True)
    assert dimmed not in stripped_buffer.getvalue()
    assert dimmed.replace("\x1b", "?") in stripped_buffer.getvalue()


def test_model_switch_preserves_state(mocker):
    captured = {}

    def fake_run_loop(**kwargs):
        session = kwargs["session"]
        session.scratchpad._values["k"] = "sentinel"
        session.read_snapshots["p"] = "sentinel-snap"
        session.untrusted_observation_seen = True
        captured["session"] = session

    mock_get_provider = mocker.patch(
        "olla.repl.get_provider", return_value=(MagicMock(), "m")
    )
    mock_run_loop = mocker.patch("olla.repl.run_loop", side_effect=fake_run_loop)
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        "seed state",
        "/model other",
        EOFError(),
    ]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    assert mock_run_loop.call_count == 1  # /model itself never calls run_loop
    session = captured["session"]
    assert session.scratchpad._values == {"k": "sentinel"}
    assert session.read_snapshots == {"p": "sentinel-snap"}
    assert session.untrusted_observation_seen is True
    assert mock_get_provider.call_args_list[-1].kwargs["model"] == "other"


def test_model_switch_changes_model_used_by_next_run_loop_call(mocker):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        "/model other",
        "next task",
        EOFError(),
    ]

    main_loop(model="original", max_steps=5, system_prompt="sys")

    mock_run_loop.assert_called_once()
    assert mock_run_loop.call_args.kwargs["model"] == "other"


def test_model_switch_without_argument_prints_usage(mocker, capsys):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_run_loop = mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = ["/model", EOFError()]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    mock_run_loop.assert_not_called()
    assert "usage" in capsys.readouterr().out.lower()


def test_clear_resets_all_state(mocker):
    captured = {}

    def fake_run_loop(**kwargs):
        session = kwargs["session"]
        session.scratchpad._values["k"] = "sentinel"
        session.messages.append({"role": "user", "content": "hi"})
        session.read_snapshots["p"] = "sentinel-snap"
        session.untrusted_observation_seen = True
        captured["session"] = session

    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mocker.patch("olla.repl.run_loop", side_effect=fake_run_loop)
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        "seed state",
        "/clear",
        EOFError(),
    ]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    session = captured["session"]
    assert session.messages == []
    assert session.scratchpad._values == {}
    assert session.read_snapshots == {}
    assert session.untrusted_observation_seen is False


def test_exit_and_quit_slash_commands_end_loop_without_run_loop(mocker):
    for command in ("/exit", "/quit"):
        mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
        mock_run_loop = mocker.patch("olla.repl.run_loop")
        mock_session_cls = mocker.patch("olla.repl.PromptSession")
        mock_session_cls.return_value.prompt.side_effect = [command]

        main_loop(model="m", max_steps=5, system_prompt="sys")

        mock_run_loop.assert_not_called()


def test_slash_command_in_tool_observation_does_not_dispatch(mocker):
    def fake_run_loop(**kwargs):
        kwargs["session"].messages.append(
            {"role": "tool", "content": "/model attacker"}
        )

    mock_get_provider = mocker.patch(
        "olla.repl.get_provider", return_value=(MagicMock(), "m")
    )
    mocker.patch("olla.repl.run_loop", side_effect=fake_run_loop)
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        "task that produces the injected string",
        "ordinary follow-up text",
        EOFError(),
    ]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    switch_calls = [
        c
        for c in mock_get_provider.call_args_list
        if c.kwargs.get("model") == "attacker"
    ]
    assert switch_calls == []


def test_repeated_model_switch_is_idempotent(mocker):
    mock_get_provider = mocker.patch(
        "olla.repl.get_provider", return_value=(MagicMock(), "m")
    )
    mock_run_loop = mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        "/model x",
        "/model x",
        "ordinary turn",
        EOFError(),
    ]

    main_loop(model="original", max_steps=5, system_prompt="sys")

    switch_calls = [
        c for c in mock_get_provider.call_args_list if c.kwargs.get("model") == "x"
    ]
    assert len(switch_calls) == 2
    assert switch_calls[0].kwargs == switch_calls[1].kwargs
    mock_run_loop.assert_called_once()
    assert mock_run_loop.call_args.kwargs["model"] == "x"


def test_ctrl_c_during_turn_leaves_state_unchanged_before_next_turn(mocker):
    call_count = {"n": 0}

    def fake_run_loop(**kwargs):
        call_count["n"] += 1
        session = kwargs["session"]
        session.messages.append({"role": "user", "content": kwargs["task"]})
        if call_count["n"] == 1:
            raise KeyboardInterrupt()
        session.messages.append({"role": "assistant", "content": "ok"})

    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_run_loop = mocker.patch("olla.repl.run_loop", side_effect=fake_run_loop)
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [
        "interrupted task",
        "next task",
        EOFError(),
    ]
    mocker.patch("olla.repl.time.monotonic", return_value=0.0)

    main_loop(model="m", max_steps=5, system_prompt="sys")

    # Ctrl+C aborted the first call after only its own message was appended
    # (no partial tool-observation entries), and the loop continued to the
    # next prompt rather than exiting.
    assert mock_run_loop.call_count == 2
    session = mock_run_loop.call_args_list[0].kwargs["session"]
    assert session.messages == [
        {"role": "user", "content": "interrupted task"},
        {"role": "user", "content": "next task"},
        {"role": "assistant", "content": "ok"},
    ]


def test_main_loop_warms_encoder_at_startup(mocker):
    mocker.patch("olla.repl.get_provider", return_value=(MagicMock(), "m"))
    mock_warm_encoder = mocker.patch("olla.repl.context_trim.warm_encoder")
    mocker.patch("olla.repl.run_loop")
    mock_session_cls = mocker.patch("olla.repl.PromptSession")
    mock_session_cls.return_value.prompt.side_effect = [EOFError()]

    main_loop(model="m", max_steps=5, system_prompt="sys")

    mock_warm_encoder.assert_called_once()
    # Warmed before the first prompt() call — the mock is configured before
    # main_loop runs, so call_count==1 at this point already proves ordering
    # relative to the single prompt() call that follows it in the loop body.
    mock_session_cls.return_value.prompt.assert_called_once()
