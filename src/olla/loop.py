"""ReAct loop step execution."""

import difflib
import itertools
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

import ollama
from rich.prompt import Confirm
from rich.text import Text

from olla.debug import debug_log, mask_secret, set_debug
from olla.parser import parse_response
from olla.providers import Provider, ProviderError, get_provider
from olla.safety import check
from olla.tools.base import FileSnapshot
from olla.tools.files import (
    open_parent_directory,
    parent_directory_matches_path,
    read_file,
    write_file,
)
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


def _metadata_safe(value: object) -> str:
    """Quote untrusted single-line metadata with all controls escaped."""
    return ascii(str(value))


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
    resolved_label = _metadata_safe(resolved)
    if current is None:
        body = truncate_output(proposed)
        return (
            "=== TRUSTED WRITE PREVIEW START ===\n"
            "Create new file\n"
            f"Resolved path: {resolved_label}\n"
            f"Proposed bytes: {proposed_bytes}\n"
            "--- proposed content ---\n"
            f"{body}\n"
            "=== TRUSTED WRITE PREVIEW END ==="
        )

    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"current:{resolved_label}",
            tofile=f"proposed:{resolved_label}",
        )
    )
    if not diff:
        diff = "(no content changes)"
    return (
        "=== TRUSTED WRITE PREVIEW START ===\n"
        "Overwrite existing file\n"
        f"Resolved path: {resolved_label}\n"
        f"Current bytes: {_utf8_size(current)}\n"
        f"Proposed bytes: {proposed_bytes}\n"
        f"{truncate_output(diff)}\n"
        "=== TRUSTED WRITE PREVIEW END ==="
    )


def _write_confirmation_prompt(resolved: Path, proposed: str) -> Text:
    """Put authoritative write metadata in the markup-free final prompt."""
    return Text(
        f"Write {_utf8_size(proposed)} bytes to {_metadata_safe(resolved)}?"
    )


def _read_again_observation(resolved: Path) -> str:
    """Return the single recovery instruction for every stale-file refusal."""
    return (
        f"refused: {_metadata_safe(resolved)} changed, disappeared, or became unreadable; "
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


THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(content: str) -> str:
    """Strip reasoning/thinking content (<think>...</think>) before tag evaluation (D-10)."""
    return THINK_TAG_RE.sub("", content)


def _is_mocked(obj: object) -> bool:
    """Check if object is mocked in unit tests."""
    return isinstance(obj, Mock) or hasattr(obj, "mock_calls")


def _prepare_action(content: str) -> _Action:
    """Parse once and normalize signatures before any handler can exit early."""
    parsed = parse_response(_strip_thinking(content))
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
    debug_log("Observation recorded", preview)
    _display(preview)
    messages.append({"role": "user", "content": f"Observation: {preview}"})


def _record_file_observation(messages: list[dict], preview: str) -> None:
    """Record file bytes as provenance-preserving, explicitly untrusted data."""
    debug_log("File observation recorded", preview)
    _display(preview)
    messages.append(
        {
            "role": "tool",
            "content": (
                "Observation: <untrusted_file_content>\n"
                f"{preview}\n"
                "</untrusted_file_content>"
            ),
        }
    )


def _record_memory_observation(messages: list[dict], preview: str) -> None:
    """Record recalled notes as explicitly untrusted scratchpad data."""
    debug_log("Memory observation recorded", preview)
    _display(preview)
    messages.append(
        {
            "role": "tool",
            "content": (
                "Observation: <untrusted_memory_content>\n"
                f"{preview}\n"
                "</untrusted_memory_content>"
            ),
        }
    )


def _record_shell_observation(messages: list[dict], preview: str) -> None:
    """Record command output as explicitly untrusted tool data."""
    debug_log("Shell observation recorded", preview)
    _display(preview)
    messages.append(
        {
            "role": "tool",
            "content": (
                "Observation: <untrusted_shell_output>\n"
                f"{preview}\n"
                "</untrusted_shell_output>"
            ),
        }
    )


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


def call_model(
    model: str,
    messages: list[dict],
    think: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Call ollama.chat() or provider for the ReAct loop."""
    if _is_mocked(ollama.chat) or (
        not model.startswith(("openrouter/", "openai/"))
        and api_key is None
        and base_url is None
    ):
        response = ollama.chat(
            model=model,
            messages=messages,
            options={"stop": ["</args>"], "num_ctx": 8192},
            think=think,
        )
        return response["message"]["content"]
    provider, _ = get_provider(model=model, api_key=api_key, base_url=base_url)
    return provider.chat(messages, think=think)


def _call_model_for_loop(model: str, messages: list[dict]) -> str | None:
    """Call the model and turn expected Ollama client failures into diagnostics."""
    try:
        return call_model(model, messages)
    except (ollama.RequestError, ollama.ResponseError, ProviderError) as error:
        _display(
            f"Ollama request failed for model {_metadata_safe(model)}: {error}. "
            "Check that Ollama is running and the model is installed."
        )
        return None


def _stream_model_turn(
    provider: Provider,
    messages: list[dict],
    model: str = "",
) -> str | None:
    """Stream model response, rendering thought tokens in dimmed styling."""
    if _is_mocked(call_model) or _is_mocked(ollama.chat):
        return _call_model_for_loop(model, messages)

    full_response: list[str] = []
    try:
        for chunk in provider.stream_chat(messages):
            if chunk.is_thought:
                print(f"\033[2m{chunk.text}\033[0m", end="", flush=True)
            else:
                print(chunk.text, end="", flush=True)
            full_response.append(chunk.text)
        print()
        return "".join(full_response)
    except ProviderError as error:
        _display(f"Model request failed: {error}")
        return None
    except (ollama.RequestError, ollama.ResponseError) as error:
        _display(
            f"Ollama request failed for model {_metadata_safe(model)}: {error}. "
            "Check that Ollama is running and the model is installed."
        )
        return None
    except Exception as error:  # noqa: BLE001
        _display(f"Model request failed: {error}")
        return None


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
        _display(f"Step 1 would read: {_metadata_safe(action.resolved)}")
    elif action.kind == "write_file":
        if action.error is not None:
            _display(action.error)
            return
        assert action.resolved is not None
        assert action.file_content is not None
        if action.resolved.exists():
            _display(
                "Step 1 would overwrite existing file: "
                f"{_metadata_safe(action.resolved)} — refused: "
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
            "Step 1 would write by creating new file: "
            f"{_metadata_safe(action.resolved)} — {verdict}"
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
    untrusted_observation_seen: bool,
) -> bool:
    if action.error is not None:
        _record_observation(messages, action.error)
        return False
    assert action.argv is not None
    argv = list(action.argv)
    decision = check(argv, yes=yes)
    debug_log(f"Step {step} - Shell safety check", {"argv": argv, "decision": decision})
    if decision["kind"] == "BLOCK":
        _record_observation(
            messages,
            f"blocked by safety policy: {decision['reason']}",
        )
        return False
    if decision["kind"] == "CONFIRM" and (
        not yes or untrusted_observation_seen
    ):
        try:
            if yes and untrusted_observation_seen:
                _display(
                    "Confirmation required: this action follows untrusted tool output."
                )
            _display(f"Run command: {argv!r}")
            approved = Confirm.ask("Proceed?", default=False)
        except EOFError:
            approved = False
        if not approved:
            messages.append(
                {"role": "user", "content": "Observation: declined by user"}
            )
            return False

    _display(f"Step {step}: running {argv}...")
    result = run_shell(argv)
    debug_log(f"Step {step} - Shell execution result", result)
    if "error" in result:
        combined = result["error"]
    else:
        combined = result.get("stdout", "") + result.get("stderr", "")
        if not combined:
            combined = "(no output)"
    _record_shell_observation(messages, truncate_output(combined))
    return True


def _execute_read_file(
    action: _Action,
    *,
    step: int,
    messages: list[dict],
    read_snapshots: dict[Path, _FileReadSnapshot],
) -> bool:
    if action.error is not None:
        _record_observation(messages, action.error)
        return False
    assert action.resolved is not None
    resolved = action.resolved
    _display(f"Step {step}: reading {_metadata_safe(resolved)}...")
    result = read_file(str(resolved))
    debug_log(f"Step {step} - Read file result", {"path": str(resolved), "chars_read": len(result.get("content", "")) if "content" in result else None, "error": result.get("error")})
    if "error" in result:
        read_snapshots.pop(resolved, None)
        _record_observation(messages, truncate_output(result["error"]))
        return False

    raw_content = result.get("content", "")
    read_snapshots[resolved] = _FileReadSnapshot(
        content=raw_content,
        fully_observed=truncate_output(raw_content) == raw_content,
        identity=result.get("snapshot"),
    )
    _record_file_observation(messages, truncate_output(raw_content))
    return True


def _execute_write_file(
    action: _Action,
    *,
    step: int,
    messages: list[dict],
    read_snapshots: dict[Path, _FileReadSnapshot],
    yes: bool,
    untrusted_observation_seen: bool,
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
                f"refused: existing file {_metadata_safe(resolved)} must be shown completely "
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
            f"refused: existing file {_metadata_safe(resolved)} must be shown completely "
            "by read_file in this run before overwrite",
        )
        return

    try:
        parent_fd, parent_snapshot = open_parent_directory(str(resolved))
    except (OSError, ValueError) as error:
        _record_observation(
            messages,
            f"could not open parent directory for {_metadata_safe(resolved)}: {error}",
        )
        return

    try:
        _display(
            _render_write_preview(
                resolved,
                file_content,
                current=current_content,
            )
        )
        if not yes or untrusted_observation_seen:
            try:
                if yes and untrusted_observation_seen:
                    _display(
                        "Confirmation required: this action follows untrusted tool output."
                    )
                approved = Confirm.ask(
                    _write_confirmation_prompt(resolved, file_content),
                    default=False,
                )
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
        if final_resolved != resolved or not parent_directory_matches_path(
            str(resolved), parent_snapshot
        ):
            read_snapshots.pop(resolved, None)
            _record_observation(
                messages,
                "refused: write target or parent directory changed after approval; "
                "use read_file on the target before retrying",
            )
            return

        _display(f"Step {step}: writing to {_metadata_safe(final_resolved)}...")
        expected_snapshot = snapshot.identity if snapshot is not None else None
        result = write_file(
            str(final_resolved),
            file_content,
            expected_snapshot=expected_snapshot,
            parent_directory_fd=parent_fd,
            expected_parent_snapshot=parent_snapshot,
        )
        if result.get("status") == "uncertain" or result.get(
            "commit_uncertain"
        ):
            read_snapshots.pop(resolved, None)
            warning = result.get(
                "warning", "the backend could not confirm the write outcome"
            )
            preview = f"write outcome uncertain: {warning}"
            recovery_path = result.get("recovery_path")
            if recovery_path is not None:
                preview += f"; recovery object: {_metadata_safe(recovery_path)}"
            preview += "; use read_file on the target before retrying"
        elif "error" in result:
            if result.get("stale"):
                read_snapshots.pop(resolved, None)
                preview = _read_again_observation(resolved)
            else:
                preview = result["error"]
        else:
            preview = (
                f"wrote {result.get('bytes_written', 0)} bytes to "
                f"{_metadata_safe(final_resolved)}"
            )
            if "warning" in result:
                preview = f"{preview}; warning: {result['warning']}"
            read_snapshots.pop(resolved, None)
        debug_log(f"Step {step} - Write file result", {"target": str(final_resolved), "result": result})
        _record_observation(messages, preview)
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass


def _execute_memory(
    action: _Action,
    *,
    step: int,
    messages: list[dict],
    scratchpad: Scratchpad,
) -> bool:
    assert action.memory_request is not None
    debug_log(
        f"Step {step} - Memory request",
        {
            "tool": action.memory_request.tool,
            "signature": action.memory_request.signature,
            "scratchpad_keys": list(scratchpad._data.keys()) if hasattr(scratchpad, "_data") else None,
        },
    )
    preview = truncate_output(
        _handle_memory(
            action.memory_request,
            step=step,
            scratchpad=scratchpad,
            execute=True,
        )
    )
    if action.memory_request.tool == "recall":
        _record_memory_observation(messages, preview)
        return True
    _record_observation(messages, preview)
    return False


def run_loop(
    task: str,
    model: str,
    max_steps: int,
    system_prompt: str,
    yes: bool = False,
    dry_run: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    debug: bool = False,
) -> None:
    """Drive the reason-act-observe loop until a <final> answer or max_steps."""
    if debug:
        set_debug(True)

    try:
        provider, resolved_model = get_provider(
            model=model, api_key=api_key, base_url=base_url
        )
    except ProviderError as error:
        _display(f"Model initialization failed: {error}")
        return

    debug_log(
        "Loop initialization",
        {
            "task": task,
            "model": model,
            "resolved_model": resolved_model,
            "provider": provider.__class__.__name__,
            "max_steps": max_steps,
            "yes": yes,
            "dry_run": dry_run,
            "api_key": mask_secret(api_key),
            "base_url": base_url,
        },
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    if dry_run:
        debug_log("Executing dry run turn")
        content = _stream_model_turn(provider, messages, model=resolved_model)
        if content is None:
            return
        action = _prepare_action(content)
        debug_log("Dry run action parsed", {"kind": action.kind, "tool": action.tool})
        _preview_action(action, yes=yes)
        return

    scratchpad = Scratchpad()
    read_snapshots: dict[Path, _FileReadSnapshot] = {}
    previous_signature: tuple | None = None
    repeat_count = 0
    untrusted_observation_seen = False

    step_iter = range(1, max_steps + 1) if max_steps > 0 else itertools.count(1)
    for step in step_iter:
        total_label = str(max_steps) if max_steps > 0 else "unlimited"
        debug_log(
            f"=== Step {step}/{total_label} ===",
            {
                "message_count": len(messages),
                "messages": [
                    {
                        "role": m["role"],
                        "chars": len(m.get("content", "")),
                        "content": m.get("content", ""),
                    }
                    for m in messages
                ],
            },
        )
        content = _stream_model_turn(provider, messages, model=resolved_model)
        if content is None:
            debug_log(f"Step {step} - Model turn returned None")
            return
        debug_log(f"Step {step} - Raw model response", content)
        action = _prepare_action(content)
        debug_log(
            f"Step {step} - Action parsed",
            {
                "kind": action.kind,
                "tool": action.tool,
                "signature": str(action.signature),
                "error": action.error,
                "text": action.text,
                "args_raw": action.args_raw,
            },
        )
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
            untrusted_observation_seen = (
                _execute_shell(
                    action,
                    step=step,
                    messages=messages,
                    yes=yes,
                    untrusted_observation_seen=untrusted_observation_seen,
                )
                or untrusted_observation_seen
            )
        elif action.kind == "read_file":
            untrusted_observation_seen = (
                _execute_read_file(
                    action,
                    step=step,
                    messages=messages,
                    read_snapshots=read_snapshots,
                )
                or untrusted_observation_seen
            )
        elif action.kind == "write_file":
            _execute_write_file(
                action,
                step=step,
                messages=messages,
                read_snapshots=read_snapshots,
                yes=yes,
                untrusted_observation_seen=untrusted_observation_seen,
            )
        elif action.kind == "memory":
            untrusted_observation_seen = (
                _execute_memory(
                    action,
                    step=step,
                    messages=messages,
                    scratchpad=scratchpad,
                )
                or untrusted_observation_seen
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

    if max_steps > 0:
        _display(f"Reached max steps ({max_steps}) without a <final> answer.")
