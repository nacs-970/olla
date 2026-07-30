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


def _terminal_safe(text: object) -> str:
    """Escape terminal controls and invalid Unicode while preserving newlines."""
    rendered = []
    for character in str(text):
        codepoint = ord(character)
        if character == "\n":
            rendered.append(character)
        elif codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
            rendered.append(f"\\x{codepoint:02x}")
        elif 0xD800 <= codepoint <= 0xDFFF:
            rendered.append(f"\\u{codepoint:04x}")
        elif not character.isprintable():
            width = 4 if codepoint <= 0xFFFF else 8
            rendered.append(f"\\u{codepoint:0{width}x}")
        else:
            rendered.append(character)
    return "".join(rendered)


def _display(text: object) -> None:
    """Print untrusted display text only after making it terminal-safe."""
    print(_terminal_safe(text))


def _utf8_size(text: str) -> str:
    try:
        return str(len(text.encode("utf-8")))
    except UnicodeEncodeError:
        return "not encodable as UTF-8"


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


@dataclass(frozen=True)
class _Action:
    """One parsed and normalized model action shared by all loop policies."""

    kind: str
    tool: str
    signature: tuple | None
    text: str = ""
    args_raw: str = ""
    argv: tuple[str, ...] | None = None
    path: str | None = None
    file_content: str | None = None
    resolved: Path | None = None
    memory_request: _MemoryRequest | None = None
    error: str | None = None


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
    proposed_bytes = _utf8_size(proposed)
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
        f"Current bytes: {_utf8_size(current)}\n"
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


def _prepare_action(content: str) -> _Action:
    """Parse once and normalize signatures before any handler can exit early."""
    parsed = parse_response(content)
    if parsed["type"] == "final":
        return _Action("final", "final", None, text=parsed["text"])
    if parsed["type"] == "none":
        return _Action("none", "response", ("none", content), text=content)

    tool = parsed["tool"]
    args_raw = parsed["args_raw"]
    if tool == "shell":
        try:
            argv = tuple(shlex.split(args_raw))
        except ValueError as error:
            message = (
                "error: could not parse shell command "
                f"(mismatched quotes: {error}). Please fix the quotes and try again."
            )
            return _Action(
                "shell",
                tool,
                ("shell", "malformed", args_raw),
                args_raw=args_raw,
                error=message,
            )
        return _Action(
            "shell",
            tool,
            ("shell", argv),
            args_raw=args_raw,
            argv=argv,
        )

    if tool == "read_file":
        resolved, error = _resolve_file_path(args_raw)
        normalized = str(resolved) if resolved is not None else args_raw
        return _Action(
            "read_file",
            tool,
            ("read_file", normalized),
            args_raw=args_raw,
            resolved=resolved,
            error=error,
        )

    if tool == "write_file":
        path, separator, file_content = args_raw.partition("\n")
        path = path.strip()
        if separator == "":
            error = (
                f"refused: write_file for {path!r} had no content line — "
                "nothing written"
            )
            return _Action(
                "write_file",
                tool,
                ("write_file", "invalid", path, "missing-content-line"),
                args_raw=args_raw,
                path=path,
                error=error,
            )
        resolved, error = _resolve_file_path(path)
        normalized = str(resolved) if resolved is not None else path
        return _Action(
            "write_file",
            tool,
            ("write_file", "valid", normalized, file_content),
            args_raw=args_raw,
            path=path,
            file_content=file_content,
            resolved=resolved,
            error=error,
        )

    if tool in {"remember", "recall"}:
        request = _prepare_memory_request(tool, args_raw)
        return _Action(
            "memory",
            tool,
            request.signature,
            args_raw=args_raw,
            memory_request=request,
        )

    return _Action(
        "unknown",
        tool,
        ("unknown", tool, args_raw),
        args_raw=args_raw,
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
        _display(f"Step {step}: remembering {call.key}...")
        result = scratchpad.remember(call)
    else:
        key = request.recall_key
        assert key is not None
        if not execute:
            return f"Step {step} would recall: {key}"
        assert scratchpad is not None
        _display(f"Step {step}: recalling {key}...")
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
    _display(preview)
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


def _preview_action(action: _Action, *, yes: bool) -> None:
    """Run the shared validation path and display a dry-run preview."""
    if action.kind == "final":
        _display(f"Model would answer directly: {action.text}")
    elif action.kind == "none":
        _display(f"Model produced no valid <tool>/<final> tag: {action.text}")
    elif action.kind == "shell":
        if action.error is not None:
            _display(action.error)
            return
        assert action.argv is not None
        decision = check(list(action.argv), yes=yes)
        if decision["kind"] == "ALLOW":
            verdict = "auto-approved (read-only allowlist)"
        elif decision["kind"] == "CONFIRM":
            verdict = "would prompt for confirmation"
        else:
            verdict = f"BLOCKED: {decision['reason']}"
        _display(f"Step 1 would run: {list(action.argv)} — {verdict}")
    elif action.kind == "read_file":
        if action.error is not None:
            _display(action.error)
            return
        assert action.resolved is not None
        _display(f"Step 1 would read: {action.resolved}")
    elif action.kind == "write_file":
        if action.error is not None:
            _display(action.error)
            return
        assert action.resolved is not None
        assert action.file_content is not None
        if action.resolved.exists():
            _display(
                f"Step 1 would overwrite existing file: {action.resolved} — refused: "
                "read_file must show the complete current file in this run first"
            )
            return
        _display(
            _render_write_preview(
                action.resolved,
                action.file_content,
                current=None,
            )
        )
        verdict = "auto-approved by --yes" if yes else "would prompt for confirmation"
        _display(
            f"Step 1 would write by creating new file: {action.resolved} — {verdict}"
        )
    elif action.kind == "memory":
        assert action.memory_request is not None
        _display(
            _handle_memory(
                action.memory_request,
                step=1,
                scratchpad=None,
                execute=False,
            )
        )
    else:
        _display(f"Model would call unknown tool '{action.tool}'")


def _execute_shell(
    action: _Action,
    *,
    step: int,
    messages: list[dict],
    yes: bool,
) -> None:
    if action.error is not None:
        _record_observation(messages, action.error)
        return
    assert action.argv is not None
    argv = list(action.argv)
    decision = check(argv, yes=yes)
    if decision["kind"] == "BLOCK":
        _record_observation(
            messages,
            f"blocked by safety policy: {decision['reason']}",
        )
        return
    if decision["kind"] == "CONFIRM" and not yes:
        try:
            _display(f"Run command: {argv!r}")
            approved = Confirm.ask("Proceed?", default=False)
        except EOFError:
            approved = False
        if not approved:
            messages.append(
                {"role": "user", "content": "Observation: declined by user"}
            )
            return

    _display(f"Step {step}: running {argv}...")
    result = run_shell(argv)
    if "error" in result:
        combined = result["error"]
    else:
        combined = result.get("stdout", "") + result.get("stderr", "")
        if not combined:
            combined = "(no output)"
    _record_observation(messages, truncate_output(combined))


def _execute_read_file(
    action: _Action,
    *,
    step: int,
    messages: list[dict],
    read_snapshots: dict[Path, _FileReadSnapshot],
) -> None:
    if action.error is not None:
        _record_observation(messages, action.error)
        return
    assert action.resolved is not None
    resolved = action.resolved
    _display(f"Step {step}: reading {resolved}...")
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
        combined = raw_content or "(no output)"
    _record_observation(messages, truncate_output(combined))


def _execute_write_file(
    action: _Action,
    *,
    step: int,
    messages: list[dict],
    read_snapshots: dict[Path, _FileReadSnapshot],
    yes: bool,
) -> None:
    if action.error is not None:
        _record_observation(messages, action.error)
        return
    assert action.path is not None
    assert action.file_content is not None
    assert action.resolved is not None
    path = action.path
    file_content = action.file_content
    resolved = action.resolved

    target_existed = resolved.exists()
    current_content: str | None = None
    snapshot = read_snapshots.get(resolved)
    if snapshot is not None:
        if (
            not snapshot.fully_observed
            or snapshot.identity is None
        ):
            _record_observation(
                messages,
                f"refused: existing file {resolved} must be shown completely "
                "by read_file in this run before overwrite",
            )
            return
        current_result = read_file(str(resolved))
        if (
            "error" in current_result
            or current_result.get("content", "") != snapshot.content
            or current_result.get("snapshot") != snapshot.identity
        ):
            read_snapshots.pop(resolved, None)
            _record_observation(messages, _read_again_observation(resolved))
            return
        current_content = snapshot.content
    elif target_existed:
        _record_observation(
            messages,
            f"refused: existing file {resolved} must be shown completely "
            "by read_file in this run before overwrite",
        )
        return

    _display(
        _render_write_preview(
            resolved,
            file_content,
            current=current_content,
        )
    )
    if not yes:
        try:
            approved = Confirm.ask("Proceed?", default=False)
        except EOFError:
            approved = False
        if not approved:
            messages.append(
                {"role": "user", "content": "Observation: declined by user"}
            )
            return

    final_resolved, error = _resolve_file_path(path)
    if error is not None:
        _record_observation(messages, error)
        return
    assert final_resolved is not None
    if final_resolved != resolved:
        read_snapshots.pop(resolved, None)
        _record_observation(
            messages,
            f"refused: write target changed from {resolved} to {final_resolved}; "
            "use read_file on the target before retrying",
        )
        return

    _display(f"Step {step}: writing to {final_resolved}...")
    expected_snapshot = snapshot.identity if snapshot is not None else None
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
            f"wrote {result.get('bytes_written', 0)} bytes to {final_resolved}"
        )
        if "warning" in result:
            preview = f"{preview}; warning: {result['warning']}"
        read_snapshots.pop(resolved, None)
    _record_observation(messages, preview)


def _execute_memory(
    action: _Action,
    *,
    step: int,
    messages: list[dict],
    scratchpad: Scratchpad,
) -> None:
    assert action.memory_request is not None
    preview = _handle_memory(
        action.memory_request,
        step=step,
        scratchpad=scratchpad,
        execute=True,
    )
    _record_observation(messages, preview)


def run_loop(
    task: str,
    model: str,
    max_steps: int,
    system_prompt: str,
    yes: bool = False,
    dry_run: bool = False,
) -> None:
    """Drive the reason-act-observe loop until a <final> answer or max_steps."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    if dry_run:
        _preview_action(_prepare_action(call_model(model, messages)), yes=yes)
        return

    scratchpad = Scratchpad()
    read_snapshots: dict[Path, _FileReadSnapshot] = {}
    previous_signature: tuple | None = None
    repeat_count = 0

    for step in range(1, max_steps + 1):
        content = call_model(model, messages)
        action = _prepare_action(content)
        history_content = truncate_output(content) if action.kind == "none" else content
        messages.append({"role": "assistant", "content": history_content})

        if action.kind == "final":
            _display(action.text)
            return

        assert action.signature is not None
        previous_signature, repeat_count, stop = _track_repetition(
            action.tool,
            action.signature,
            previous_signature,
            repeat_count,
        )
        if stop is not None:
            _display(stop)
            return

        if action.kind == "shell":
            _execute_shell(action, step=step, messages=messages, yes=yes)
        elif action.kind == "read_file":
            _execute_read_file(
                action,
                step=step,
                messages=messages,
                read_snapshots=read_snapshots,
            )
        elif action.kind == "write_file":
            _execute_write_file(
                action,
                step=step,
                messages=messages,
                read_snapshots=read_snapshots,
                yes=yes,
            )
        elif action.kind == "memory":
            _execute_memory(
                action,
                step=step,
                messages=messages,
                scratchpad=scratchpad,
            )
        elif action.kind == "unknown":
            _record_observation(messages, f"unknown tool '{action.tool}'")
        else:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "No <tool> or <final> tag found. Respond using "
                        "<tool>/<args> or <final> only."
                    ),
                }
            )

    _display(f"Reached max steps ({max_steps}) without a <final> answer.")
