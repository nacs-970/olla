"""ReAct loop step execution."""

import shlex

import ollama

from olla.parser import parse_response
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


def run_loop(task: str, model: str, max_steps: int, system_prompt: str) -> None:
    """Drive the reason-act-observe loop until a <final> answer or max_steps."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    for step in range(1, max_steps + 1):
        content = call_model(model, messages)
        parsed = parse_response(content)
        history_content = truncate_output(content) if parsed["type"] == "none" else content
        messages.append({"role": "assistant", "content": history_content})

        if parsed["type"] == "final":
            print(parsed["text"])
            return

        if parsed["type"] == "tool":
            try:
                argv = shlex.split(parsed["args_raw"])
            except ValueError as e:
                preview = f"error: could not parse command: {e}"
                print(preview)
                messages.append({"role": "user", "content": f"Observation: {preview}"})
                continue
            print(f"Step {step}: running {argv}...")
            result = run_shell(parsed["args_raw"])
            if "error" in result:
                combined = result["error"]
            elif "stdout" in result or "stderr" in result:
                combined = result.get("stdout", "") + result.get("stderr", "")
            else:
                combined = "(no output)"
            preview = truncate_output(combined)
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
