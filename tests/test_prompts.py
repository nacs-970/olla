"""Contract tests for the concise five-tool system prompt."""

import re

from olla.prompts import SYSTEM_PROMPT


def test_system_prompt_advertises_five_tools():
    tool_line = next(
        line for line in SYSTEM_PROMPT.splitlines() if "tools available" in line
    )

    assert "5 tools available" in tool_line
    assert set(re.findall(r"`([^`]+)`", tool_line)) == {
        "shell",
        "read_file",
        "write_file",
        "remember",
        "recall",
    }


def test_system_prompt_teaches_memory_formats():
    assert "<tool>remember</tool><args>key\nvalue</args>" in SYSTEM_PROMPT
    assert "<tool>recall</tool><args>key</args>" in SYSTEM_PROMPT
    assert "key on the first line" in SYSTEM_PROMPT
    assert "value on all remaining lines" in SYSTEM_PROMPT


def test_system_prompt_contains_one_memory_round_trip():
    transcript = """<tool>remember</tool><args>meeting_time
3pm</args>
Observation: remembered: meeting_time

<tool>recall</tool><args>meeting_time</args>
Observation: 3pm

<final>The meeting is at 3pm.</final>"""

    assert SYSTEM_PROMPT.count(transcript) == 1


def test_system_prompt_preserves_shell_file_guidance():
    assert "<tool>shell</tool><args>the raw shell command to run</args>" in SYSTEM_PROMPT
    assert "<tool>read_file</tool><args>" in SYSTEM_PROMPT
    assert "path/to/file</args>" in SYSTEM_PROMPT
    assert "<tool>write_file</tool><args>" in SYSTEM_PROMPT
    assert "file content goes here\non one or more lines</args>" in SYSTEM_PROMPT
    assert (
        "Never include a literal </args> sequence inside file content or a "
        "remembered value"
    ) in SYSTEM_PROMPT
    assert SYSTEM_PROMPT.count("Example:") == 4
    assert "Observation: meeting at 3pm" in SYSTEM_PROMPT
    assert "Observation: wrote 15 bytes to" in SYSTEM_PROMPT
    assert "Observation: total 0" in SYSTEM_PROMPT


def test_system_prompt_does_not_teach_automatic_memory_or_compaction():
    lowered = SYSTEM_PROMPT.lower()

    assert "automatic memory" not in lowered
    assert "inject all" not in lowered
    assert "compact" not in lowered
