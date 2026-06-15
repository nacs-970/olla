"""ReAct loop step execution."""

import shlex
from pathlib import Path

import ollama
from rich.prompt import Confirm

from olla.parser import parse_response
from olla.safety import check
from olla.tools.files import read_file, write_file
from olla.tools.shell import run_shell

MAX_OBSERVATION_CHARS = 2000


def truncate_output(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    """Truncate text to a head+tail preview if it exceeds `limit` chars."""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2):]
    return f"{head}\n[...truncated {len(text) - limit} chars...]\n{tail}"


def call_model(model: str, messages: list[dict], think: bool = False) -> str:
    """Call ollama.chat() with the stop-sequences and context size for the ReAct loop."""
    response = ollama.chat(model=model, messages=messages, options={"stop": ["</args>", "Observation:"], "num_ctx": 8192}, think=think)
    return response["message"]["content"]


def run_loop(task: str, model: str, max_steps: int, system_prompt: str, yes: bool = False, dry_run: bool = False) -> None:
    """Drive the reason-act-observe loop until a <final> answer or max_steps."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

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
            path, _, _ = parsed["args_raw"].partition("\n")
            resolved = Path(path.strip()).resolve()
            print(f"Step 1 would write to {resolved} — would prompt for confirmation")
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
                if sig == prev_sig:
                    repeat_count += 1
                else:
                    prev_sig = sig
                    repeat_count = 1

                if repeat_count >= 3:
                    print(f"olla stopped: same {parsed['tool']} call repeated 3x — model likely stuck")
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
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue
            elif parsed["tool"] == "write_file":
                sig = ("write_file", parsed["args_raw"])
                if sig == prev_sig:
                    repeat_count += 1
                else:
                    prev_sig = sig
                    repeat_count = 1

                if repeat_count >= 3:
                    print(f"olla stopped: same {parsed['tool']} call repeated 3x — model likely stuck")
                    return

                path, _, file_content = parsed["args_raw"].partition("\n")
                path = path.strip()
                resolved = Path(path).resolve()

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
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue
            else:
                preview = f"unknown tool '{parsed['tool']}'"
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue

        messages.append(
            {
                "role": "user",
                "content": "No <tool> or <final> tag found. Respond using <tool>/<args> or <final> only.",
            }
        )

    print(f"Reached max steps ({max_steps}) without a <final> answer.")
