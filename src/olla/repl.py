"""Minimal prompt_toolkit REPL controller (REPL-01/REPL-02, D-01/D-02)."""

import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout

from olla import context_trim
from olla.loop import SessionState, run_loop
from olla.providers import ProviderError, get_provider
from olla.tools.memory import Scratchpad

# Second Ctrl+C arriving within this window of the first exits the session (D-12).
DOUBLE_TAP_THRESHOLD_SECONDS = 1.5

# Persistent REPL input history location (prompt_toolkit FileHistory, REPL-01).
# NOTE (T-07-04): this file is plaintext — anything typed at the REPL prompt,
# including a pasted secret, is written to disk unredacted, the same as any
# shell history file. No redaction is implemented for REPL input in this phase.
_HISTORY_FILENAME = ".olla_history"


def _build_key_bindings() -> KeyBindings:
    """Bind Alt+Enter to insert a newline, leaving plain Enter bound to
    prompt_toolkit's own default single-line submit behavior."""
    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _insert_newline(event) -> None:
        event.current_buffer.insert_text("\n")

    return kb


def main_loop(
    model: str,
    max_steps: int,
    system_prompt: str,
    yes: bool = False,
    dry_run: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    debug: bool = False,
) -> None:
    """Drive an interactive multi-turn session, calling run_loop() once per turn.

    One SessionState is constructed for the whole process and shared across every
    run_loop() call (D-01/D-02/D-05). `current_model` is a mutable loop-scoped seam —
    the `/model <name>` handler reassigns it so the next turn executes against the
    switched-to model without resetting any other session state.

    Ctrl+C is handled at two sites: while idle at the prompt (raised by
    `PromptSession.prompt()` via its default `interrupt_exception=KeyboardInterrupt`)
    and mid-turn while `run_loop()` is running (Python's default SIGINT handling
    raises KeyboardInterrupt in the main thread regardless of what it is blocked on).
    A single Ctrl+C at either site aborts only the in-flight prompt/turn and returns
    to the `> ` prompt; a second Ctrl+C within `DOUBLE_TAP_THRESHOLD_SECONDS` of the
    first (at either site) exits the session (D-12).
    """
    try:
        get_provider(model=model, api_key=api_key, base_url=base_url)
    except ProviderError as error:
        print(f"REPL failed to initialize model '{model}': {error}")
        return

    # Warm the tiktoken encoder once at startup (Pitfall 1) so the ~3.5s cold
    # fetch cost is paid here, with a visible message, rather than landing
    # unexplained mid-conversation at the first trim-check.
    context_trim.warm_encoder()

    current_model = model
    session_state = SessionState(
        messages=[], scratchpad=Scratchpad(), read_snapshots={}
    )
    history_path = Path.home() / _HISTORY_FILENAME
    session_prompt = PromptSession(
        history=FileHistory(str(history_path)),
        multiline=False,
        key_bindings=_build_key_bindings(),
    )

    last_interrupt: float | None = None

    def _is_double_tap() -> bool:
        """Record this Ctrl+C's timestamp; return True if it arrived within the
        double-tap exit threshold of the previous one (D-12)."""
        nonlocal last_interrupt
        now = time.monotonic()
        double_tap = (
            last_interrupt is not None
            and (now - last_interrupt) <= DOUBLE_TAP_THRESHOLD_SECONDS
        )
        last_interrupt = now
        return double_tap

    while True:
        try:
            text = session_prompt.prompt("> ")
        except KeyboardInterrupt:
            if _is_double_tap():
                break
            continue
        except EOFError:
            break

        if not text.strip():
            continue

        if text.startswith("/"):
            command, *rest = text.split(maxsplit=1)
            argument = rest[0].strip() if rest else ""

            if command in ("/exit", "/quit"):
                break

            if command == "/model":
                if not argument:
                    print("Usage: /model <name>")
                    continue
                try:
                    # Config-level validation gate only (D-06/D-17) — confirms
                    # the model string parses and resolves to a provider; for
                    # the local Ollama path this does NOT confirm the model
                    # itself exists or loads (OllamaProvider makes no network
                    # call), only the next real provider.chat() call does.
                    get_provider(model=argument, api_key=api_key, base_url=base_url)
                except ProviderError as error:
                    print(f"Failed to switch to model '{argument}': {error}")
                    continue
                current_model = argument
                print(f"Switched to model '{current_model}'")
                continue

            if command == "/clear":
                session_state.messages = []
                session_state.scratchpad = Scratchpad()
                session_state.read_snapshots = {}
                session_state.untrusted_observation_seen = False
                print("Session cleared.")
                continue

            print(f"Unknown command: {command}")
            continue

        try:
            with patch_stdout():
                run_loop(
                    task=text,
                    model=current_model,
                    max_steps=max_steps,
                    system_prompt=system_prompt,
                    yes=yes,
                    dry_run=dry_run,
                    api_key=api_key,
                    base_url=base_url,
                    debug=debug,
                    session=session_state,
                )
        except KeyboardInterrupt:
            if _is_double_tap():
                break
            continue
