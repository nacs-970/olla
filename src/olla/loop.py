"""ReAct loop step execution."""

import difflib
import shlex
from dataclasses import dataclass
from pathlib import Path

import ollama
from rich.prompt import Confirm

from olla.parser import parse_response
from olla.safety import check
from olla.tools.base import FileSnapshot
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


@dataclass(frozen=True)
class _FileReadSnapshot:
    """Content and descriptor identity observed during this run."""

    content: str
    fully_observed: bool
    identity: FileSnapshot | None


def _resolve_file_path(path: str) -> tuple[Path | None, str | None]:
    """Resolve an untrusted model path without letting pathlib errors escape."""
    try:
        return Path(path).resolve(), None
    except (OSError, ValueError, RuntimeError) as error:
        return None, f"error: could not resolve file path {path!r}: {error}"


def _render_write_preview(
    resolved: Path,
    proposed: str,
    *,
    current: str | None,
) -> str:
    """Render a bounded local-only create or overwrite preview."""
    proposed_bytes = len(proposed.encode("utf-8"))
    if current is None:
        body = truncate_output(proposed)
        return (
            "Create new file\n"
            f"Resolved path: {resolved}\n"
            f"Proposed bytes: {proposed_bytes}\n"
            "--- proposed content ---\n"
            f"{body}"
        )

    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"current:{resolved}",
            tofile=f"proposed:{resolved}",
        )
    )
    if not diff:
        diff = "(no content changes)"
    return (
        "Overwrite existing file\n"
        f"Resolved path: {resolved}\n"
        f"Current bytes: {len(current.encode('utf-8'))}\n"
        f"Proposed bytes: {proposed_bytes}\n"
        f"{truncate_output(diff)}"
    )


def _read_again_observation(resolved: Path) -> str:
    """Return the single recovery instruction for every stale-file refusal."""
    return (
        f"refused: {resolved} changed, disappeared, or became unreadable; "
        "use read_file on it again before retrying write_file"
    )


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
                print(f"error: could not parse shell command (mismatched quotes: {e}). Please fix the quotes and try again.")
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
            resolved, error = _resolve_file_path(parsed["args_raw"])
            if error is not None:
                print(error)
                return
            assert resolved is not None
            print(f"Step 1 would read: {resolved}")
            return
        elif parsed["tool"] == "write_file":
            path, sep, file_content = parsed["args_raw"].partition("\n")
            path = path.strip()
            if sep == "":
                print(
                    f"Step 1 write_file for {path!r} — refused: no content line provided, nothing would be written"
                )
                return

            resolved, error = _resolve_file_path(path)
            if error is not None:
                print(error)
                return
            assert resolved is not None
            if resolved.exists():
                print(
                    f"Step 1 would overwrite existing file: {resolved} — refused: "
                    "read_file must show the complete current file in this run first"
                )
                return

            print(
                _render_write_preview(
                    resolved,
                    file_content,
                    current=None,
                )
            )
            verdict = "auto-approved by --yes" if yes else "would prompt for confirmation"
            print(
                f"Step 1 would write by creating new file: {resolved} — {verdict}"
            )
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

    read_snapshots: dict[Path, _FileReadSnapshot] = {}
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
                    preview = f"error: could not parse shell command (mismatched quotes: {e}). Please fix the quotes and try again."
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

                resolved, error = _resolve_file_path(parsed["args_raw"])
                if error is not None:
                    _record_observation(messages, error)
                    continue
                assert resolved is not None
                print(f"Step {step}: reading {resolved}...")

                result = read_file(str(resolved))
                if "error" in result:
                    read_snapshots.pop(resolved, None)
                    combined = result["error"]
                else:
                    raw_content = result.get("content", "")
                    read_snapshots[resolved] = _FileReadSnapshot(
                        content=raw_content,
                        fully_observed=truncate_output(raw_content) == raw_content,
                        identity=result.get("snapshot"),
                    )
                    combined = raw_content
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

                if sep == "":
                    # CR-03: no newline means no content line was provided at all.
                    # Refuse unconditionally (even under --yes) to prevent silent
                    # truncation of an existing file to 0 bytes.
                    preview = (
                        f"refused: write_file for {path!r} had no content line — nothing written"
                    )
                    _record_observation(messages, preview)
                    continue

                resolved, error = _resolve_file_path(path)
                if error is not None:
                    _record_observation(messages, error)
                    continue
                assert resolved is not None

                target_existed = resolved.exists()
                current_content: str | None = None
                snapshot: _FileReadSnapshot | None = None
                if target_existed:
                    snapshot = read_snapshots.get(resolved)
                    if (
                        snapshot is None
                        or not snapshot.fully_observed
                        or snapshot.identity is None
                    ):
                        preview = (
                            f"refused: existing file {resolved} must be shown completely "
                            "by read_file in this run before overwrite"
                        )
                        _record_observation(messages, preview)
                        continue

                    current_result = read_file(str(resolved))
                    if (
                        "error" in current_result
                        or current_result.get("content", "") != snapshot.content
                        or current_result.get("snapshot") != snapshot.identity
                    ):
                        read_snapshots.pop(resolved, None)
                        _record_observation(
                            messages,
                            _read_again_observation(resolved),
                        )
                        continue
                    current_content = snapshot.content

                print(
                    _render_write_preview(
                        resolved,
                        file_content,
                        current=current_content,
                    )
                )

                if not yes:
                    try:
                        operation = (
                            "Overwrite existing file"
                            if target_existed
                            else "Create new file"
                        )
                        approved = Confirm.ask(
                            f"{operation} `{resolved}`?",
                            default=False,
                        )
                    except EOFError:
                        approved = False
                    if not approved:
                        messages.append({"role": "user", "content": "Observation: declined by user"})
                        continue

                final_resolved, error = _resolve_file_path(path)
                if error is not None:
                    _record_observation(messages, error)
                    continue
                assert final_resolved is not None
                if final_resolved != resolved:
                    read_snapshots.pop(resolved, None)
                    _record_observation(
                        messages,
                        (
                            f"refused: write target changed from {resolved} to "
                            f"{final_resolved}; use read_file on the target before retrying"
                        ),
                    )
                    continue

                print(f"Step {step}: writing to {final_resolved}...")

                expected_snapshot = (
                    snapshot.identity
                    if target_existed and snapshot is not None
                    else None
                )
                result = write_file(
                    str(final_resolved),
                    file_content,
                    expected_snapshot=expected_snapshot,
                )
                if "error" in result:
                    if result.get("stale"):
                        read_snapshots.pop(resolved, None)
                        preview = _read_again_observation(resolved)
                    else:
                        preview = result["error"]
                else:
                    preview = (
                        f"wrote {result.get('bytes_written', 0)} bytes to "
                        f"{final_resolved}"
                    )
                    read_snapshots.pop(resolved, None)
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
