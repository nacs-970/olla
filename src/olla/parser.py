"""Tolerant, ordered parser for <tool>/<args>/<final> model output."""

import re

FINAL_RE = re.compile(r"<final>(.*?)(?:</final>|$)", re.DOTALL | re.IGNORECASE)
TOOL_OPEN_RE = re.compile(r"<tool>", re.IGNORECASE)
TOOL_CLOSE_RE = re.compile(r"</tool>", re.IGNORECASE)
ARGS_OPEN_RE = re.compile(r"<args>", re.IGNORECASE)
ARGS_CLOSE_RE = re.compile(r"</args>", re.IGNORECASE)


def _args_payload_spans(content: str) -> list[tuple[int, int]]:
    """Return spans that may contain literal protocol-looking payload text."""
    spans = []
    for opening in ARGS_OPEN_RE.finditer(content):
        closing = ARGS_CLOSE_RE.search(content, opening.end())
        end = closing.start() if closing is not None else len(content)
        spans.append((opening.end(), end))
    return spans


def _outside_spans(position: int, spans: list[tuple[int, int]]) -> bool:
    return all(not (start <= position < end) for start, end in spans)


def parse_response(content: str) -> dict:
    """Tolerantly extract <tool>/<args>/<final> from model output.

    Markdown fences and surrounding prose are tolerated. A single outer
    ``<final>`` wins; otherwise exactly one ordered tool/args pair is required.

    write_file, remember, and recall are special-cased: their <args> payloads
    can contain protocol-looking text and must not be fence-stripped.
    """
    args_spans = _args_payload_spans(content)
    outer_finals = [
        match
        for match in FINAL_RE.finditer(content)
        if _outside_spans(match.start(), args_spans)
    ]
    if len(outer_finals) == 1:
        return {"type": "final", "text": outer_finals[0].group(1).strip()}
    if len(outer_finals) > 1:
        return {"type": "none", "raw": content}

    # Identify special tools from the envelope before their payload. Once the
    # outer <args> opens, file and memory content is opaque and may contain
    # protocol-looking text without creating additional calls.
    first_args_open = ARGS_OPEN_RE.search(content)
    if first_args_open is not None:
        prefix_end = first_args_open.start()
        prefix_tool_openings = list(TOOL_OPEN_RE.finditer(content, 0, prefix_end))
        prefix_tool_closings = list(TOOL_CLOSE_RE.finditer(content, 0, prefix_end))
        prefix_args_closings = list(ARGS_CLOSE_RE.finditer(content, 0, prefix_end))
        if (
            len(prefix_tool_openings) == 1
            and len(prefix_tool_closings) <= 1
            and not prefix_args_closings
        ):
            tool_open = prefix_tool_openings[0]
            if prefix_tool_closings:
                tool_close = prefix_tool_closings[0]
                valid_tool_close = tool_open.end() <= tool_close.start()
                tool_end = tool_close.start()
            else:
                valid_tool_close = True
                tool_end = prefix_end

            tool = content[tool_open.end() : tool_end].strip()
            if valid_tool_close and tool in {"write_file", "remember", "recall"}:
                args_close = ARGS_CLOSE_RE.search(content, first_args_open.end())
                if args_close is None:
                    args_end = len(content)
                else:
                    args_end = args_close.start()
                    suffix = content[args_close.end() :]
                    suffix_finals = list(FINAL_RE.finditer(suffix))
                    if len(suffix_finals) == 1:
                        return {
                            "type": "final",
                            "text": suffix_finals[0].group(1).strip(),
                        }
                    if len(suffix_finals) > 1:
                        return {"type": "none", "raw": content}
                    if any(
                        pattern.search(suffix) is not None
                        for pattern in (
                            TOOL_OPEN_RE,
                            TOOL_CLOSE_RE,
                            ARGS_OPEN_RE,
                            ARGS_CLOSE_RE,
                        )
                    ):
                        return {"type": "none", "raw": content}

                args_raw = content[first_args_open.end() : args_end]
                if tool == "recall":
                    args_raw = args_raw.strip()
                return {"type": "tool", "tool": tool, "args_raw": args_raw}

    tool_openings = list(TOOL_OPEN_RE.finditer(content))
    args_openings = list(ARGS_OPEN_RE.finditer(content))
    tool_closings = list(TOOL_CLOSE_RE.finditer(content))
    args_closings = list(ARGS_CLOSE_RE.finditer(content))

    # Independent searches can accidentally pair unrelated blocks. Requiring
    # one ordered structure also rejects duplicated and nested calls.
    if len(tool_openings) != 1 or len(args_openings) != 1:
        return {"type": "none", "raw": content}
    tool_open = tool_openings[0]
    args_open = args_openings[0]
    if args_open.start() < tool_open.end():
        return {"type": "none", "raw": content}

    if len(tool_closings) > 1 or len(args_closings) > 1:
        return {"type": "none", "raw": content}
    if tool_closings:
        tool_close = tool_closings[0]
        if not (tool_open.end() <= tool_close.start() <= args_open.start()):
            return {"type": "none", "raw": content}
        tool_end = tool_close.start()
    else:
        tool_end = args_open.start()

    if args_closings:
        args_close = args_closings[0]
        if args_close.start() < args_open.end():
            return {"type": "none", "raw": content}
        args_end = args_close.start()
    else:
        args_end = len(content)

    tool = content[tool_open.end() : tool_end].strip()
    if not tool:
        return {"type": "none", "raw": content}
    args_raw = content[args_open.end() : args_end]
    return {
        "type": "tool",
        "tool": tool,
        "args_raw": args_raw.strip(),
    }
