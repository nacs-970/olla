"""Tests for the bounded invocation-local memory tool."""

import pytest

from olla.tools.memory import (
    MAX_KEYS,
    MAX_TOTAL_CHARS,
    MAX_VALUE_CHARS,
    RememberCall,
    Scratchpad,
    parse_recall_args,
    parse_remember_args,
)


@pytest.mark.parametrize(
    ("args_raw", "expected"),
    [
        ("\nvalue", (None, "invalid remember: key must not be empty")),
        ("   \nvalue", (None, "invalid remember: key must not be empty")),
        (
            "key",
            (
                None,
                "invalid remember: expected key on first line and value on remaining lines",
            ),
        ),
        ("  MixedCase  \n", (RememberCall("MixedCase", ""), None)),
        (" key \n  value\n", (RememberCall("key", "  value\n"), None)),
    ],
)
def test_parse_remember_args_contract(args_raw, expected):
    assert parse_remember_args(args_raw) == expected


def test_parse_remember_args_rejects_oversized_value():
    value = "x" * (MAX_VALUE_CHARS + 1)

    assert parse_remember_args(f"key\n{value}") == (
        None,
        f"memory value too large: {MAX_VALUE_CHARS + 1} characters; maximum is {MAX_VALUE_CHARS}",
    )


@pytest.mark.parametrize(
    ("args_raw", "expected"),
    [
        ("", (None, "invalid recall: key must not be empty")),
        (" \n\t ", (None, "invalid recall: key must not be empty")),
        ("  MixedCase  ", ("MixedCase", None)),
    ],
)
def test_parse_recall_args_contract(args_raw, expected):
    assert parse_recall_args(args_raw) == expected


def test_scratchpad_remember_recall_and_replace_contract():
    scratchpad = Scratchpad()

    assert scratchpad.remember(RememberCall("key", "first")) == {
        "content": "remembered: key"
    }
    assert scratchpad.recall("key") == {"content": "first"}
    assert scratchpad.remember(RememberCall("key", "second")) == {
        "content": "remembered: key"
    }
    assert scratchpad.recall("key") == {"content": "second"}
    assert scratchpad.recall("Key") == {"error": "memory not found: Key"}


def test_scratchpad_rejects_empty_keys_at_public_boundary():
    scratchpad = Scratchpad()

    assert scratchpad.remember(RememberCall("", "secret")) == {
        "error": "invalid remember: key must not be empty"
    }
    assert scratchpad.remember(RememberCall("   ", "secret")) == {
        "error": "invalid remember: key must not be empty"
    }
    assert scratchpad.recall("") == {
        "error": "invalid recall: key must not be empty"
    }
    assert scratchpad.recall(" \t ") == {
        "error": "invalid recall: key must not be empty"
    }


def test_scratchpad_normalizes_keys_at_public_boundary():
    scratchpad = Scratchpad()

    assert scratchpad.remember(RememberCall("  MixedCase  ", "value")) == {
        "content": "remembered: MixedCase"
    }
    assert scratchpad.recall("MixedCase") == {"content": "value"}
    assert scratchpad.recall("  MixedCase  ") == {"content": "value"}


def test_scratchpad_empty_and_whitespace_values():
    scratchpad = Scratchpad()

    assert scratchpad.remember(RememberCall("empty", "")) == {
        "content": "remembered empty: empty"
    }
    assert scratchpad.recall("empty") == {"content": "memory is empty: empty"}

    whitespace = " \t\n "
    assert scratchpad.remember(RememberCall("spaces", whitespace)) == {
        "content": "remembered: spaces"
    }
    assert scratchpad.recall("spaces") == {"content": whitespace}


def test_scratchpad_value_limit_is_atomic():
    scratchpad = Scratchpad()
    assert scratchpad.remember(RememberCall("key", "old")) == {
        "content": "remembered: key"
    }

    oversized = "x" * (MAX_VALUE_CHARS + 1)
    assert scratchpad.remember(RememberCall("key", oversized)) == {
        "error": (
            f"memory value too large: {MAX_VALUE_CHARS + 1} characters; "
            f"maximum is {MAX_VALUE_CHARS}"
        )
    }
    assert scratchpad.recall("key") == {"content": "old"}
    assert scratchpad.remember(RememberCall("boundary", "x" * MAX_VALUE_CHARS)) == {
        "content": "remembered: boundary"
    }


def test_scratchpad_key_limit_is_atomic_and_allows_replacement():
    scratchpad = Scratchpad()
    for index in range(MAX_KEYS):
        assert scratchpad.remember(RememberCall(f"key-{index}", "")) == {
            "content": f"remembered empty: key-{index}"
        }

    assert scratchpad.remember(RememberCall("overflow", "")) == {
        "error": f"memory key limit reached: maximum is {MAX_KEYS}"
    }
    assert scratchpad.recall("overflow") == {
        "error": "memory not found: overflow"
    }
    assert scratchpad.remember(RememberCall("key-0", "replacement")) == {
        "content": "remembered: key-0"
    }
    assert scratchpad.recall("key-0") == {"content": "replacement"}
    assert scratchpad.remember(RememberCall("still-overflow", "")) == {
        "error": f"memory key limit reached: maximum is {MAX_KEYS}"
    }


def test_scratchpad_total_capacity_is_atomic_and_reuses_freed_space():
    scratchpad = Scratchpad()
    full_value = "x" * MAX_VALUE_CHARS
    for index in range(MAX_TOTAL_CHARS // MAX_VALUE_CHARS):
        assert scratchpad.remember(RememberCall(f"key-{index}", full_value)) == {
            "content": f"remembered: key-{index}"
        }

    assert scratchpad.remember(RememberCall("overflow", "x")) == {
        "error": (
            "memory capacity exceeded: "
            f"write would use {MAX_TOTAL_CHARS + 1} of {MAX_TOTAL_CHARS} characters"
        )
    }
    assert scratchpad.recall("overflow") == {
        "error": "memory not found: overflow"
    }
    assert scratchpad.recall("key-0") == {"content": full_value}

    shorter = full_value[:-1]
    assert scratchpad.remember(RememberCall("key-0", shorter)) == {
        "content": "remembered: key-0"
    }
    assert scratchpad.remember(RememberCall("now-fits", "x")) == {
        "content": "remembered: now-fits"
    }
    assert scratchpad.recall("now-fits") == {"content": "x"}


def test_scratchpad_rejected_replacement_preserves_capacity_accounting():
    scratchpad = Scratchpad()
    assert scratchpad.remember(RememberCall("keep", "k" * MAX_VALUE_CHARS)) == {
        "content": "remembered: keep"
    }
    for index in range(1, MAX_TOTAL_CHARS // MAX_VALUE_CHARS):
        assert scratchpad.remember(
            RememberCall(f"key-{index}", "x" * MAX_VALUE_CHARS)
        ) == {"content": f"remembered: key-{index}"}

    assert scratchpad.remember(
        RememberCall("keep", "z" * (MAX_VALUE_CHARS + 1))
    ) == {
        "error": (
            f"memory value too large: {MAX_VALUE_CHARS + 1} characters; "
            f"maximum is {MAX_VALUE_CHARS}"
        )
    }
    assert scratchpad.recall("keep") == {"content": "k" * MAX_VALUE_CHARS}

    assert scratchpad.remember(RememberCall("keep", "k" * (MAX_VALUE_CHARS - 1))) == {
        "content": "remembered: keep"
    }
    assert scratchpad.remember(RememberCall("later", "x")) == {
        "content": "remembered: later"
    }


def test_scratchpad_instances_are_isolated():
    first = Scratchpad()
    second = Scratchpad()

    assert first.remember(RememberCall("key", "value")) == {
        "content": "remembered: key"
    }
    assert first.recall("key") == {"content": "value"}
    assert second.recall("key") == {"error": "memory not found: key"}
