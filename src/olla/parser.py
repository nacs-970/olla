"""Tolerant XML-tag parser for <tool>/<args>/<final> model output."""

import re

FINAL_RE = re.compile(r"<final>(.*?)(?:</final>|$)", re.DOTALL | re.IGNORECASE)
TOOL_RE = re.compile(r"<tool>(.*?)(?:</tool>|$)", re.DOTALL | re.IGNORECASE)
ARGS_RE = re.compile(r"<args>(.*?)(?:</args>|$)", re.DOTALL | re.IGNORECASE)


def parse_response(content: str) -> dict:
    """Tolerantly extract <tool>/<args>/<final> from model output.

    Strips markdown code fences, then prefers <final> if present, else a
    complete <tool>+<args> pair, else returns the original raw content.

    write_file and remember are special-cased: their <args> payloads contain
    verbatim content and must not be fence-stripped or whitespace-trimmed.
    """
    raw_tool_match = TOOL_RE.search(content)
    raw_args_match = ARGS_RE.search(content)
    if (
        raw_tool_match
        and raw_args_match
        and raw_tool_match.group(1).strip() in {"write_file", "remember"}
    ):
        tool = raw_tool_match.group(1).strip()
        return {
            "type": "tool",
            "tool": tool,
            "args_raw": raw_args_match.group(1),
        }

    stripped = re.sub(r"```[a-zA-Z]*\n?|```", "", content)

    final_match = FINAL_RE.search(stripped)
    if final_match:
        return {"type": "final", "text": final_match.group(1).strip()}

    tool_match = TOOL_RE.search(stripped)
    args_match = ARGS_RE.search(stripped)
    if tool_match and args_match:
        return {
            "type": "tool",
            "tool": tool_match.group(1).strip(),
            "args_raw": args_match.group(1).strip(),
        }

    return {"type": "none", "raw": content}
