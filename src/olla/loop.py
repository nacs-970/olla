"""ReAct loop step execution."""

import shlex
from dataclasses import dataclass
from pathlib import Path

import ollama
from rich.prompt import Confirm

from olla.parser import parse_response
from olla.safety import check
from olla.tools.files import read_file, write_file
from olla.tools.memory import (
    RememberCall,
    Scratchpad,
    parse_recall_args,
    parse_remember_args,
)
from olla.tools.shell import run_shell

MAX_OBSERVATION_CHARS = 2000


@dataclass(frozen=True)
class _MemoryRequest:
    """One normalized memory request shared by preview and execution paths."""

    tool: str
    signature: tuple
    remember_call: RememberCall | None = None
    recall_key: str | None = None
    error: str | None = None


def _prepare_memory_request(tool: str, args_raw: str) -> _MemoryRequest:
    """Parse memory arguments once and build the normalized repeat signature."""
    if tool == "remember":
        call, error = parse_remember_args(args_raw)
        signature = (
            ("remember", args_raw)
            if call is None
            else ("remember", call.key, call.value)
        )
        return _MemoryRequest(
            tool=tool,
            signature=signature,
            remember_call=call,
            error=error,
        )

    key, error = parse_recall_args(args_raw)
    signature = ("recall", args_raw) if key is None else ("recall", key)
    return _MemoryRequest(
        tool=tool,
        signature=signature,
        recall_key=key,
        error=error,
    )


def _handle_memory(
    request: _MemoryRequest,
    *,
    step: int,
    scratchpad: Scratchpad | None,
    execute: bool,
) -> str:
    """Render a memory preview or execute it without duplicating policy."""
    if request.error is not None:
        return request.error

    if request.tool == "remember":
        call = request.remember_call
        assert call is not None
        if not execute:
            return f"Step {step} would remember: {call.key} ({len(call.value)} chars)"
        assert scratchpad is not None
        print(f"Step {step}: remembering {call.key}...")
        result = scratchpad.remember(call)
    else:
        key = request.recall_key
        assert key is not None
        if not execute:
            return f"Step {step} would recall: {key}"
        assert scratchpad is not None
        print(f"Step {step}: recalling {key}...")
        result = scratchpad.recall(key)

    return result.get("error", result.get("content", ""))


def _track_repetition(
    tool: str,
    signature: tuple,
    previous: tuple | None,
    count: int,
) -> tuple[tuple, int, str | None]:
    """Update the shared consecutive-call counter and report a stuck model."""
    next_count = count + 1 if signature == previous else 1
    stop = None
    if next_count >= 3:
        stop = f"olla stopped: same {tool} call repeated 3x — model likely stuck"
    return signature, next_count, stop


def _record_observation(messages: list[dict], preview: str) -> None:
    """Print and append the exact same tool result as an Observation."""
    print(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})


def truncate_output(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    """Truncate text to a head+tail preview if it exceeds `limit` chars."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if len(text) <= limit:
        return text
    head_len = limit // 2
    tail_len = limit - head_len
    head = text[:head_len]
    tail = text[-tail_len:] if tail_len else ""
    return f"{head}\n[...truncated {len(text) - limit} chars...]\n{tail}"


def call_model(model: str, messages: list[dict], think: bool = False) -> str:
    """Call ollama.chat() with the stop-sequences and context size for the ReAct loop."""
    response = ollama.chat(
        model=model,
        messages=messages,
        options={"stop": ["</args>"], "num_ctx": 8192},
        think=think,
    )
    return response["message"]["content"]


def run_loop(task: str, model: str, max_steps: int, system_prompt: str, yes: bool = False, dry_run: bool = False) -> None:
    """Drive the reason-act-observe loop until a <final> answer or max_steps."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    scratchpad = Scratchpad()

    if dry_run:
        content = call_model(model, messages)
        parsed = parse_response(content)

        if parsed["type"] == "final":
            print(f"Model would answer directly: {parsed['text']}")
            return

        if parsed["type"] == "none":
            print(f"Model produced no valid <tool>/<final> tag: {content}")
            return

        if parsed["tool"] == "shell":
            try:
                argv = shlex.split(parsed["args_raw"])
            except ValueError as e:
                print(f"error: could not parse command: {e}")
                return

            decision = check(argv, yes=yes)
            if decision["kind"] == "ALLOW":
                verdict = "auto-approved (read-only allowlist)"
            elif decision["kind"] == "CONFIRM":
                verdict = "would prompt for confirmation"
            else:
                verdict = f"BLOCKED: {decision['reason']}"

            print(f"Step 1 would run: {argv} — {verdict}")
            return
        elif parsed["tool"] == "read_file":
            print(f"Step 1 would read: {parsed['args_raw']}")
            return
        elif parsed["tool"] == "write_file":
            path, sep, _ = parsed["args_raw"].partition("\n")
            resolved = Path(path.strip()).resolve()
            if sep == "":
                print(
                    f"Step 1 would write to {resolved} — refused: no content line provided, nothing would be written"
                )
            else:
                print(f"Step 1 would write to {resolved} — would prompt for confirmation")
            return
        elif parsed["tool"] in {"remember", "recall"}:
            request = _prepare_memory_request(parsed["tool"], parsed["args_raw"])
            print(
                _handle_memory(
                    request,
                    step=1,
                    scratchpad=None,
                    execute=False,
                )
            )
            return
        else:
            print(f"Model would call unknown tool '{parsed['tool']}'")
            return

    prev_sig: tuple | None = None
    repeat_count = 0

    for step in range(1, max_steps + 1):
        content = call_model(model, messages)
        parsed = parse_response(content)
        history_content = truncate_output(content) if parsed["type"] == "none" else content
        messages.append({"role": "assistant", "content": history_content})

        if parsed["type"] == "final":
            print(parsed["text"])
            return

        if parsed["type"] == "tool":
            if parsed["tool"] == "shell":
                try:
                    argv = shlex.split(parsed["args_raw"])
                except ValueError as e:
                    preview = f"error: could not parse command: {e}"
                    print(preview)
                    messages.append({"role": "user", "content": f"Observation: {preview}"})
                    continue

                sig = ("shell", tuple(argv))
                if sig == prev_sig:
                    repeat_count += 1
                else:
                    prev_sig = sig
                    repeat_count = 1

                if repeat_count >= 3:
                    print(f"olla stopped: same {parsed['tool']} call repeated 3x — model likely stuck")
                    return

                decision = check(argv, yes=yes)

                if decision["kind"] == "BLOCK":
                    preview = f"blocked by safety policy: {decision['reason']}"
                    print(preview)
                    messages.append({"role": "user", "content": f"Observation: {preview}"})
                    continue

                if decision["kind"] == "CONFIRM" and not yes:
                    try:
                        approved = Confirm.ask(f"Run `{' '.join(argv)}`?", default=False)
                    except EOFError:
                        approved = False
                    if not approved:
                        messages.append({"role": "user", "content": "Observation: declined by user"})
                        continue

                print(f"Step {step}: running {argv}...")

                result = run_shell(argv)
                if "error" in result:
                    combined = result["error"]
                else:
                    combined = result.get("stdout", "") + result.get("stderr", "")
                    if not combined:
                        combined = "(no output)"
                preview = truncate_output(combined)
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue
            elif parsed["tool"] == "read_file":
                sig = ("read_file", parsed["args_raw"])
                prev_sig, repeat_count, stop = _track_repetition(
                    parsed["tool"], sig, prev_sig, repeat_count
                )
                if stop is not None:
                    print(stop)
                    return

                print(f"Step {step}: reading {parsed['args_raw']}...")

                result = read_file(parsed["args_raw"])
                if "error" in result:
                    combined = result["error"]
                else:
                    combined = result.get("content", "")
                    if not combined:
                        combined = "(no output)"
                preview = truncate_output(combined)
                _record_observation(messages, preview)
                continue
            elif parsed["tool"] == "write_file":
                sig = ("write_file", parsed["args_raw"])
                prev_sig, repeat_count, stop = _track_repetition(
                    parsed["tool"], sig, prev_sig, repeat_count
                )
                if stop is not None:
                    print(stop)
                    return

                path, sep, file_content = parsed["args_raw"].partition("\n")
                path = path.strip()
                resolved = Path(path).resolve()

                if sep == "":
                    # CR-03: no newline means no content line was provided at all.
                    # Refuse unconditionally (even under --yes) to prevent silent
                    # truncation of an existing file to 0 bytes.
                    preview = (
                        f"refused: write_file for {resolved} had no content line — nothing written"
                    )
                    _record_observation(messages, preview)
                    continue

                if not yes:
                    try:
                        approved = Confirm.ask(f"Write to `{resolved}`?", default=False)
                    except EOFError:
                        approved = False
                    if not approved:
                        messages.append({"role": "user", "content": "Observation: declined by user"})
                        continue

                print(f"Step {step}: writing to {resolved}...")

                result = write_file(path, file_content)
                if "error" in result:
                    preview = result["error"]
                else:
                    preview = f"wrote {result.get('bytes_written', 0)} bytes to {resolved}"
                _record_observation(messages, preview)
                continue
            elif parsed["tool"] in {"remember", "recall"}:
                request = _prepare_memory_request(
                    parsed["tool"], parsed["args_raw"]
                )
                prev_sig, repeat_count, stop = _track_repetition(
                    parsed["tool"], request.signature, prev_sig, repeat_count
                )
                if stop is not None:
                    print(stop)
                    return

                preview = _handle_memory(
                    request,
                    step=step,
                    scratchpad=scratchpad,
                    execute=True,
                )
                _record_observation(messages, preview)
                continue
            else:
                preview = f"unknown tool '{parsed['tool']}'"
                _record_observation(messages, preview)
                continue

        messages.append(
            {
                "role": "user",
                "content": "No <tool> or <final> tag found. Respond using <tool>/<args> or <final> only.",
            }
        )

    print(f"Reached max steps ({max_steps}) without a <final> answer.")
