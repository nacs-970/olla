"""Minimal prompt_toolkit REPL controller (REPL-01/REPL-02, D-01/D-02)."""

from prompt_toolkit import PromptSession

from olla.loop import SessionState, run_loop
from olla.providers import ProviderError, get_provider
from olla.tools.memory import Scratchpad


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
    07-02's `/model <name>` handler reassigns it so the next turn executes against the
    switched-to model without resetting any other session state.
    """
    try:
        get_provider(model=model, api_key=api_key, base_url=base_url)
    except ProviderError as error:
        print(f"REPL failed to initialize model '{model}': {error}")
        return

    current_model = model
    session_state = SessionState(
        messages=[], scratchpad=Scratchpad(), read_snapshots={}
    )
    session_prompt = PromptSession()

    while True:
        try:
            text = session_prompt.prompt("> ")
        except KeyboardInterrupt:
            continue
        except EOFError:
            break

        if not text.strip():
            continue

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
