"""Measure olla's per-turn prompt overhead: XML-tag tool calling vs JSON function calling.

Goal
----
olla claims its XML-tag tool protocol cuts per-turn prompt overhead. This
script produces a defensible per-turn prompt-token number for that claim by
sending the same first-turn requests to ONE OpenRouter model through three
arms. Because all arms hit the same model, they share one tokenizer and one
chat template, so their prompt-token counts are directly comparable.

Arms
----
- ``xml``: olla's production ``SYSTEM_PROMPT`` (imported from ``olla.prompts``,
  never retyped) with the production stop sequence ``["</args>"]``.
- ``xml_noex``: ``SYSTEM_PROMPT`` truncated before its first ``Example:`` line
  (derived by ``derive_noex_prompt``), same stop. It isolates how much of the
  xml-vs-native gap the few-shot examples account for.
- ``native``: ``NATIVE_SYSTEM_PROMPT`` plus the same 9 tools as OpenAI-format
  JSON function schemas (``NATIVE_TOOLS``), sent with ``tools``.

``NATIVE_SYSTEM_PROMPT`` is DERIVED from ``SYSTEM_PROMPT`` by
``derive_native_prompt``, so both arms carry the same behavioural policy text.
Stripping the few-shot Example blocks and the tag-format rules from the native
arm is INTENTIONAL: they exist only to teach the tag format, so they are part
of the XML mechanism's overhead. The per-tool behaviour sentences (for example
"This runs immediately without asking for confirmation.") are MOVED into the
native tool-schema descriptions, not deleted, so each fact is stated exactly
once in each arm.

Measurement
-----------
Each call is a non-streaming POST to ``/chat/completions``. OpenRouter's
``usage.prompt_tokens`` is counted with the model's native tokenizer and is the
full prompt count even when part of the prompt is served from cache;
``cached_tokens`` is recorded separately. Missing counts are stored as None,
excluded from every mean, and the excluded count is reported. A failing call
is recorded as an error and the run continues; the output JSON is rewritten
after every call. Arm order follows a balanced cycle (rotations, then
reversed rotations; ABBA for two arms). A 429 for OpenRouter's daily free-model
limit (``free-models-per-day``) is not retried and stops the run, because it
cannot succeed before the daily reset.

Caveats (also printed in the report)
------------------------------------
- Only the xml arms send the production stop sequence. If an upstream ignores
  ``stop``, xml completion tokens include the text after the closing args tag.
  Prompt tokens, the headline, are unaffected.
- ``provider.require_parameters`` is sent on the native arm only, to guarantee
  the upstream supports ``tools``. It is NOT sent on the xml arm: several
  tool-capable models do not list ``stop`` in ``supported_parameters``, and
  ``require_parameters`` would then leave the xml arm with no endpoint.
  Production sends ``stop`` without it, and upstreams ignore an unsupported
  ``stop``.
- No sampling temperature is set, matching production.
- Each call is a first-turn request only; this is not a full task run.
- Upstream provider routing may differ per call; the report warns when the
  arms were served by different upstream providers for a task.
- The system prompt and tool definitions are re-sent on every turn, so the
  prompt delta is a per-turn overhead.

Usage
-----
    python scripts/benchmark_tool_overhead.py --model openrouter/<id> --output results.json
    python scripts/benchmark_tool_overhead.py --model openrouter/<id> --repeats 4 --output r.json
    python scripts/benchmark_tool_overhead.py --print-prompts   # offline, no API key
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx

from olla.prompts import SYSTEM_PROMPT
from olla.providers import OpenAICompatProvider, ProviderError, get_provider

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

TASKS: list[tuple[str, str]] = [
    ("shell_task", "List the files in the current directory using the shell."),
    (
        "file_read_task",
        "Read the contents of README.md and tell me what the project is called.",
    ),
    (
        "file_write_task",
        "Create a file named notes.txt containing the single line: benchmark test.",
    ),
    (
        "multi_step_task",
        "First list the files in the current directory, then read the first Python "
        "file you find under src/, then summarize what it does.",
        # Measured as a single first-turn call like the other tasks — see the
        # module docstring's caveats. This is NOT executed as a real multi-step
        # run; the model's response to turn 1 is all that's measured.
    ),
]

# ---------------------------------------------------------------------------
# Native system prompt, derived from SYSTEM_PROMPT
# ---------------------------------------------------------------------------

# Opening or closing tool/args/final tag prefix. The word boundary (not a
# closing ">") also catches the `<tool=name>` and `<tool name="...">` variants.
TAG_RE = re.compile(r"</?(?:tool|args|final)\b")

FORMAT_MARKERS = ("respond with:", "tag block", "outside the tags")

NATIVE_FINAL_LINE = "When you have the final answer for the user, reply with plain text."


def derive_native_prompt(xml_prompt: str) -> str:
    """Derive the native-arm system prompt from the XML-arm system prompt.

    A line-level state machine over ``xml_prompt.splitlines()``; ``in_block``
    starts False. Rules, applied in order to each line:

    (a) A line whose stripped value is "Example:" stops processing. All
        Example blocks (with their blank lines, untagged payload lines, and
        Observation lines) sit at the end of SYSTEM_PROMPT, so everything from
        the first one on is dropped. A test guards this ordering assumption.
    (b) A blank line resets ``in_block`` to False and is emitted as a blank.
    (c) While ``in_block`` is True, lines are dropped.
    (d) A line starting with "To " (with the trailing space, so that
        "Tool-role messages" is not matched) opens a format-introduction
        block: set ``in_block`` and drop the line. This removes multi-line
        intros whose continuation lines carry no tags, and the per-tool
        behaviour sentences, which live in the tool-schema descriptions.
    (e) A line matching TAG_RE is dropped.
    (f) A line that STARTS WITH "Observation:" is dropped (startswith, not a
        substring test: "Use its latest Observation as ..." is policy).
    (g) A line containing any FORMAT_MARKERS entry is dropped. The final
        paragraph mixes lines to drop with the NEVER-use-shell line to keep,
        which is why the rules work line by line.
    (h) Every other line is kept.

    Consecutive blank lines are then collapsed, leading and trailing blanks are
    stripped, and a blank line plus NATIVE_FINAL_LINE is appended.
    """
    kept: list[str] = []
    in_block = False
    for line in xml_prompt.splitlines():
        stripped = line.strip()
        if stripped == "Example:":  # (a)
            break
        if not stripped:  # (b)
            in_block = False
            kept.append("")
            continue
        if in_block:  # (c)
            continue
        if line.startswith("To "):  # (d)
            in_block = True
            continue
        if TAG_RE.search(line):  # (e)
            continue
        if line.startswith("Observation:"):  # (f)
            continue
        if any(marker in line for marker in FORMAT_MARKERS):  # (g)
            continue
        kept.append(line)  # (h)

    collapsed: list[str] = []
    for line in kept:
        if line == "" and collapsed and collapsed[-1] == "":
            continue
        collapsed.append(line)
    while collapsed and collapsed[0] == "":
        collapsed.pop(0)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return "\n".join(collapsed) + "\n\n" + NATIVE_FINAL_LINE + "\n"


NATIVE_SYSTEM_PROMPT = derive_native_prompt(SYSTEM_PROMPT)


def derive_noex_prompt(xml_prompt: str) -> str:
    """Return ``xml_prompt`` truncated before its first "Example:" line."""
    lines = xml_prompt.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "Example:":
            lines = lines[:index]
            break
    return "\n".join(lines).rstrip() + "\n"


XML_NOEX_SYSTEM_PROMPT = derive_noex_prompt(SYSTEM_PROMPT)


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


_STR = {"type": "string"}

# Every word here adds to the native arm's prompt count, so descriptions are
# kept to the facts the XML arm states once in its prompt, and no more.
NATIVE_TOOLS: list[dict] = [
    _tool("read_file", "Read a file.", {"path": _STR}, ["path"]),
    _tool(
        "write_file",
        "Write a file.",
        {"path": _STR, "content": _STR},
        ["path", "content"],
    ),
    _tool(
        "shell",
        "Run a shell command.",
        {"command": {"type": "string", "description": "The raw shell command to run."}},
        ["command"],
    ),
    _tool(
        "remember",
        "Store a scratchpad note under a key, preserving the value.",
        {"key": _STR, "value": _STR},
        ["key", "value"],
    ),
    _tool(
        "recall",
        "Retrieve one scratchpad note by its trimmed key.",
        {"key": _STR},
        ["key"],
    ),
    _tool(
        "list_dir",
        "List the contents of a directory. This runs immediately without asking "
        "for confirmation.",
        {"path": _STR},
        ["path"],
    ),
    _tool(
        "grep_files",
        "Search for a regex pattern in text files. This tool is case-sensitive, "
        "automatically skips `.git` and binary files, and runs immediately without "
        "asking for confirmation.",
        {
            "pattern": _STR,
            "path": _STR,
            "recursive": {
                "type": "boolean",
                "description": "Search subdirectories too. Omit to search only the "
                "top-level directory.",
            },
        },
        ["pattern", "path"],
    ),
    _tool(
        "search_web",
        "Search the web. This returns up to 5 numbered results, each a 3-line card "
        "(title, url, summary). This runs immediately without asking for "
        "confirmation.",
        {"query": _STR},
        ["query"],
    ),
    _tool(
        "fetch_url",
        "Fetch a webpage's readable text. This strips boilerplate (scripts, styles, "
        "navigation, headers, footers) and truncates the result to a sentence "
        "boundary. This runs immediately without asking for confirmation.",
        {"url": _STR},
        ["url"],
    ),
]

# ---------------------------------------------------------------------------
# Arms and request bodies
# ---------------------------------------------------------------------------

ARMS = ("xml", "xml_noex", "native")
XML_ARMS = ("xml", "xml_noex")
XML_STOP = ["</args>"]
NATIVE_PROVIDER_PREFS = {"require_parameters": True}


def build_body(arm: str, model_id: str, task_text: str) -> dict:
    """Build the /chat/completions body for one arm. No temperature, ever."""
    if arm in XML_ARMS:
        system = SYSTEM_PROMPT if arm == "xml" else XML_NOEX_SYSTEM_PROMPT
        return {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": task_text},
            ],
            "stop": list(XML_STOP),
            "stream": False,
        }
    if arm == "native":
        return {
            "model": model_id,
            "messages": [
                {"role": "system", "content": NATIVE_SYSTEM_PROMPT},
                {"role": "user", "content": task_text},
            ],
            "tools": NATIVE_TOOLS,
            "provider": dict(NATIVE_PROVIDER_PREFS),
            "stream": False,
        }
    raise ValueError(f"Unknown arm: {arm}")


def build_headers(api_key: str) -> dict:
    """The four headers production sends (see OpenAICompatProvider)."""
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/olla/olla",
        "X-Title": "olla CLI Agent",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Scheduling and statistics
# ---------------------------------------------------------------------------


def arm_cycle(arms: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Rotations of ``arms`` followed by rotations of the reversed arms.

    Over one full cycle every arm holds every position equally often. For two
    arms this is ABBA.
    """
    forward = list(arms)
    backward = forward[::-1]
    n = len(forward)
    rotations = [tuple(forward[i:] + forward[:i]) for i in range(n)]
    reversed_rotations = [tuple(backward[i:] + backward[:i]) for i in range(n)]
    return rotations + reversed_rotations


def build_schedule(
    repeats: int, arms: tuple[str, ...] = ARMS
) -> list[tuple[str, str, int, tuple[str, ...]]]:
    """Return (task_name, task_text, repeat, order) entries in balanced order.

    Task-major: k = task_idx * repeats + repeat indexes ``arm_cycle(arms)``.
    Do NOT use k = repeat * len(TASKS) + task_idx: with 4 tasks and a 4-long
    cycle, every task would get the same first arm on every repeat.
    """
    cycle = arm_cycle(arms)
    schedule = []
    for task_idx, (task_name, task_text) in enumerate(TASKS):
        for repeat in range(repeats):
            k = task_idx * repeats + repeat
            schedule.append((task_name, task_text, repeat + 1, cycle[k % len(cycle)]))
    return schedule


def mean_excluding_none(values) -> tuple[float | None, int]:
    """Return (mean of non-None values, number of None values)."""
    values = list(values)
    valid = [v for v in values if v is not None]
    excluded = len(values) - len(valid)
    if not valid:
        return None, excluded
    return sum(valid) / len(valid), excluded


def sum_excluding_none(values) -> tuple[int | None, int]:
    """Return (sum of non-None values, number of None values)."""
    values = list(values)
    valid = [v for v in values if v is not None]
    excluded = len(values) - len(valid)
    if not valid:
        return None, excluded
    return sum(valid), excluded


def signed_pct(xml_mean: float | None, native_mean: float | None) -> float | None:
    """(xml - native) / native * 100, or None if undefined."""
    if xml_mean is None or native_mean is None or native_mean == 0:
        return None
    return (xml_mean - native_mean) / native_mean * 100


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

RETRY_DELAYS = (2, 4, 8)
REQUEST_TIMEOUT = 120.0
ERROR_BODY_LIMIT = 300
DAILY_LIMIT_MARKER = "free-models-per-day"


def post_with_retry(client, url: str, headers: dict, body: dict, sleep=None):
    """POST once, retrying 429 and 5xx up to len(RETRY_DELAYS) times.

    Returns (http_status, parsed_json, error). Response bodies and exception
    text are truncated to ERROR_BODY_LIMIT characters.
    """
    if sleep is None:
        sleep = time.sleep
    attempt = 0
    try:
        while True:
            resp = client.post(url, headers=headers, json=body)
            status = resp.status_code
            if status == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    return status, None, f"invalid JSON: {str(exc)[:ERROR_BODY_LIMIT]}"
                if isinstance(data, dict) and "error" in data:
                    return status, data, json.dumps(data["error"])[:ERROR_BODY_LIMIT]
                return status, data, None
            if status == 429 and DAILY_LIMIT_MARKER in resp.text:
                return status, None, f"HTTP {status}: {resp.text[:ERROR_BODY_LIMIT]}"
            retryable = status == 429 or 500 <= status < 600
            if retryable and attempt < len(RETRY_DELAYS):
                sleep(RETRY_DELAYS[attempt])
                attempt += 1
                continue
            return status, None, f"HTTP {status}: {resp.text[:ERROR_BODY_LIMIT]}"
    except Exception as exc:  # noqa: BLE001 - any failure becomes a recorded error
        return None, None, f"{type(exc).__name__}: {str(exc)[:ERROR_BODY_LIMIT]}"


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def extract_record(arm, task, repeat, status, data, error) -> dict:
    """Flatten one call into a record. Absent values stay None, never 0."""
    data = _as_dict(data)
    usage = _as_dict(data.get("usage"))
    prompt_details = _as_dict(usage.get("prompt_tokens_details"))
    completion_details = _as_dict(usage.get("completion_tokens_details"))
    choices = data.get("choices")
    first_choice = _as_dict(choices[0]) if isinstance(choices, list) and choices else {}
    return {
        "arm": arm,
        "task": task,
        "repeat": repeat,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": prompt_details.get("cached_tokens"),
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
        "provider": data.get("provider"),
        "finish_reason": first_choice.get("finish_reason"),
        "http_status": status,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Output and report
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2))


def _fmt(value, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def summarize(records: list[dict]) -> dict:
    """Per-(arm, task) and per-arm None-aware means, totals, and the headline."""
    task_names = [name for name, _ in TASKS]
    per_arm_task: dict[str, dict[str, dict]] = {}
    per_arm: dict[str, dict] = {}
    for arm in ARMS:
        arm_recs = [r for r in records if r["arm"] == arm]
        per_arm_task[arm] = {}
        for task in task_names:
            recs = [r for r in arm_recs if r["task"] == task]
            p_mean, p_excl = mean_excluding_none(r["prompt_tokens"] for r in recs)
            c_mean, c_excl = mean_excluding_none(r["completion_tokens"] for r in recs)
            per_arm_task[arm][task] = {
                "calls": len(recs),
                "valid_prompt_calls": len(recs) - p_excl,
                "mean_prompt_tokens": p_mean,
                "mean_completion_tokens": c_mean,
                "providers": sorted({r["provider"] for r in recs if r["provider"]}),
            }
        p_mean, p_excl = mean_excluding_none(r["prompt_tokens"] for r in arm_recs)
        c_mean, c_excl = mean_excluding_none(r["completion_tokens"] for r in arm_recs)
        cached, cached_excl = sum_excluding_none(r["cached_tokens"] for r in arm_recs)
        reasoning, reasoning_excl = sum_excluding_none(
            r["reasoning_tokens"] for r in arm_recs
        )
        per_arm[arm] = {
            "calls": len(arm_recs),
            "errors": sum(1 for r in arm_recs if r["error"]),
            "mean_prompt_tokens": p_mean,
            "mean_completion_tokens": c_mean,
            "total_cached_tokens": cached,
            "total_reasoning_tokens": reasoning,
            "excluded": {
                "prompt_tokens": p_excl,
                "completion_tokens": c_excl,
                "cached_tokens": cached_excl,
                "reasoning_tokens": reasoning_excl,
            },
        }
    prompt_by_arm = {
        arm: signed_pct(
            per_arm[arm]["mean_prompt_tokens"], per_arm["native"]["mean_prompt_tokens"]
        )
        for arm in XML_ARMS
    }
    completion_by_arm = {
        arm: signed_pct(
            per_arm[arm]["mean_completion_tokens"],
            per_arm["native"]["mean_completion_tokens"],
        )
        for arm in XML_ARMS
    }
    return {
        "per_arm_task": per_arm_task,
        "per_arm": per_arm,
        "prompt_signed_pct": prompt_by_arm["xml"],
        "completion_signed_pct": completion_by_arm["xml"],
        "prompt_signed_pct_by_arm": prompt_by_arm,
        "completion_signed_pct_by_arm": completion_by_arm,
    }


def print_report(summary: dict) -> None:
    per_arm_task = summary["per_arm_task"]
    per_arm = summary["per_arm"]
    echo = click.echo

    echo("")
    echo("Per-(arm, task) means:")
    echo(f"  {'arm':<8} {'task':<16} {'prompt':>9} {'completion':>11} {'valid':>6}")
    for arm in ARMS:
        for task, row in per_arm_task[arm].items():
            echo(
                f"  {arm:<8} {task:<16} {_fmt(row['mean_prompt_tokens']):>9} "
                f"{_fmt(row['mean_completion_tokens']):>11} "
                f"{row['valid_prompt_calls']:>3}/{row['calls']}"
            )

    echo("")
    echo("HEADLINE: mean prompt_tokens per turn")
    for arm in ARMS:
        echo(f"  {arm:<8} {_fmt(per_arm[arm]['mean_prompt_tokens'], 2)}")
    for arm, pct in summary["prompt_signed_pct_by_arm"].items():
        if pct is None:
            echo(f"  {arm} vs native: cannot be computed (a mean is missing or native is 0)")
        else:
            echo(f"  {arm} vs native: {pct:+.2f}%  (({arm} - native) / native * 100)")

    echo("")
    echo("Completion tokens (reported separately, NOT part of the headline):")
    for arm in ARMS:
        echo(f"  {arm:<8} mean {_fmt(per_arm[arm]['mean_completion_tokens'], 2)}")
    for arm, cpct in summary["completion_signed_pct_by_arm"].items():
        echo(f"  {arm} vs native: {'n/a' if cpct is None else f'{cpct:+.2f}%'}")
    echo(
        "  Caveat: the xml arms send stop at the closing args tag. If the model "
        "does not honor stop, xml completion tokens include the text after it. "
        "Prompt tokens (the headline) are unaffected."
    )

    echo("")
    echo("Cached and reasoning tokens (totals over valid values):")
    for arm in ARMS:
        row = per_arm[arm]
        echo(
            f"  {arm:<8} cached={row['total_cached_tokens']} "
            f"reasoning={row['total_reasoning_tokens']}"
        )

    echo("")
    echo("Missing counts (excluded from every mean and total, never counted as 0):")
    for arm in ARMS:
        row = per_arm[arm]
        for metric, count in row["excluded"].items():
            echo(f"  {arm:<8} {metric:<18} excluded={count}")
        echo(f"  {arm:<8} errored calls: {row['errors']}/{row['calls']}")

    tasks = list(per_arm_task["native"])
    for arm in XML_ARMS:
        for task in tasks:
            arm_row = per_arm_task[arm][task]
            native_row = per_arm_task["native"][task]
            if arm_row["valid_prompt_calls"] != native_row["valid_prompt_calls"]:
                echo(
                    f"WARNING: task {task} has {arm_row['valid_prompt_calls']} valid {arm} "
                    f"calls but {native_row['valid_prompt_calls']} valid native calls; "
                    "the per-arm means cover different task mixes."
                )
        for task in tasks:
            arm_prov = set(per_arm_task[arm][task]["providers"])
            native_prov = set(per_arm_task["native"][task]["providers"])
            if arm_prov and native_prov and arm_prov != native_prov:
                echo(
                    f"WARNING: task {task} was served by different upstream providers "
                    f"({arm}: {sorted(arm_prov)}, native: {sorted(native_prov)})."
                )

    echo("")
    echo(
        "Note: the system prompt and tool definitions are re-sent on every turn, "
        "so the prompt delta is a per-turn overhead."
    )


def print_prompts() -> None:
    click.echo("=== NATIVE_SYSTEM_PROMPT ===")
    click.echo(NATIVE_SYSTEM_PROMPT)
    click.echo("=== NATIVE_TOOLS ===")
    click.echo(json.dumps(NATIVE_TOOLS, indent=2))
    click.echo("")
    # Count the compact JSON (as sent on the wire), not the indented display.
    tools_chars = len(json.dumps(NATIVE_TOOLS))
    native_sys = len(NATIVE_SYSTEM_PROMPT)
    click.echo("=== Character counts (characters, not tokens) ===")
    click.echo(f"xml arm:      system={len(SYSTEM_PROMPT)} chars")
    click.echo(f"xml_noex arm: system={len(XML_NOEX_SYSTEM_PROMPT)} chars")
    click.echo(
        f"native arm:   system={native_sys} chars, tools JSON (compact)={tools_chars} "
        f"chars, sum={native_sys + tools_chars} chars"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--model", type=str, default=None, help="OpenRouter model, as openrouter/<id>.")
@click.option("--repeats", type=click.IntRange(min=1), default=3, show_default=True,
              help="Repeats per task (each repeat calls every arm).")
@click.option("--output", type=click.Path(path_type=Path), default=None,
              help="JSON results path (required for live runs; rewritten after every call).")
@click.option("--print-prompts", "print_prompts_flag", is_flag=True,
              help="Offline: print the native prompt, tool JSON, and character counts.")
def main(model: str | None, repeats: int, output: Path | None, print_prompts_flag: bool) -> None:
    """Benchmark per-turn prompt tokens: xml tags vs native tools on OpenRouter."""
    if print_prompts_flag:
        print_prompts()
        return

    if not model or not model.startswith("openrouter/"):
        raise click.UsageError("--model must be an OpenRouter model: openrouter/<id>.")
    if output is None:
        raise click.UsageError("Live runs need --output, so no data is lost.")

    parent = output.parent
    if not parent.exists() or not parent.is_dir() or not os.access(parent, os.W_OK):
        raise click.ClickException(
            f"Output directory {parent} does not exist or is not writable."
        )

    try:
        provider, _ = get_provider(model, timeout=REQUEST_TIMEOUT)
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc
    if not isinstance(provider, OpenAICompatProvider):
        raise click.ClickException(f"Expected an OpenRouter provider for {model}.")
    model_id = provider.model
    url = provider.base_url + "/chat/completions"
    headers = build_headers(provider.api_key)

    config = {
        "model": model,
        "model_id": model_id,
        "repeats": repeats,
        "arms": list(ARMS),
        "tasks": [{"name": name, "text": text} for name, text in TASKS],
        "xml_noex_system_prompt": XML_NOEX_SYSTEM_PROMPT,
        "native_system_prompt": NATIVE_SYSTEM_PROMPT,
        "native_tools": NATIVE_TOOLS,
        "xml_stop": XML_STOP,
        "native_provider_prefs": NATIVE_PROVIDER_PREFS,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    records: list[dict] = []
    _write_json(output, {"config": config, "records": records})

    click.echo(f"Model: {model}  repeats={repeats}  arms={list(ARMS)}  output={output}")
    daily_limit_hit = False
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        for task_name, task_text, repeat, order in build_schedule(repeats):
            if daily_limit_hit:
                break
            for arm in order:
                try:
                    body = build_body(arm, model_id, task_text)
                    status, data, error = post_with_retry(client, url, headers, body)
                    record = extract_record(arm, task_name, repeat, status, data, error)
                except Exception as exc:  # noqa: BLE001 - record and continue
                    error = f"{type(exc).__name__}: {str(exc)[:ERROR_BODY_LIMIT]}"
                    record = extract_record(arm, task_name, repeat, None, None, error)
                records.append(record)
                click.echo(
                    f"  arm={arm:<6} task={task_name:<16} rep={repeat} "
                    f"prompt={record['prompt_tokens']} "
                    f"completion={record['completion_tokens']} "
                    f"cached={record['cached_tokens']} provider={record['provider']} "
                    f"status={record['http_status']}"
                    + (f" error={record['error'][:120]}" if record["error"] else "")
                )
                _write_json(output, {"config": config, "records": records})
                if record["error"] and DAILY_LIMIT_MARKER in record["error"]:
                    click.echo(
                        "OpenRouter daily free-model limit reached; stopping. "
                        "It resets at 00:00 UTC."
                    )
                    daily_limit_hit = True
                    break

    summary = summarize(records)
    print_report(summary)
    _write_json(output, {"config": config, "records": records, "summary": summary})
    click.echo(f"\nResults written to {output}")


if __name__ == "__main__":
    main()
