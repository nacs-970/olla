"""Tests for olla.parser.parse_response."""

from olla.parser import parse_response


def test_final_tag():
    result = parse_response("<final>The answer is 42</final>")
    assert result == {"type": "final", "text": "The answer is 42"}


def test_tool_and_args():
    result = parse_response("<tool>shell</tool><args>ls -la /tmp</args>")
    assert result == {"type": "tool", "tool": "shell", "args_raw": "ls -la /tmp"}


def test_markdown_fence_tolerance():
    content = "```\n<tool>shell</tool><args>echo hi</args>\n```"
    result = parse_response(content)
    assert result == {"type": "tool", "tool": "shell", "args_raw": "echo hi"}


def test_surrounding_prose_tolerance():
    content = "Sure, I'll check that.\n<tool>shell</tool><args>pwd</args>\nLet me run this."
    result = parse_response(content)
    assert result == {"type": "tool", "tool": "shell", "args_raw": "pwd"}


def test_unclosed_args_tag_tolerance():
    content = "<tool>shell</tool><args>ls -la /tmp"
    result = parse_response(content)
    assert result == {"type": "tool", "tool": "shell", "args_raw": "ls -la /tmp"}


def test_no_recognizable_tags():
    content = "I think I should run a command but I'm not sure which one."
    result = parse_response(content)
    assert result == {"type": "none", "raw": content}


def test_final_wins_over_tool():
    content = "<tool>shell</tool><args>ls</args><final>done</final>"
    result = parse_response(content)
    assert result["type"] == "final"
