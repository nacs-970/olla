"""Format-compliance smoke test (D-07/D-08): three-way classifier + runner."""

import re

from olla.loop import call_model
from olla.prompts import SYSTEM_PROMPT

# Model's own native tool-call syntax (Qwen-style): <tool_call>{...}
NATIVE_QWEN_RE = re.compile(r"<tool_call>\s*\{", re.IGNORECASE)

# Model's own native tool-call syntax (Gemma-style): <tool>{...}
NATIVE_GEMMA_RE = re.compile(r"<tool>\s*\{", re.IGNORECASE)

# olla's compliant <tool>NAME</tool><args> tags. Negative lookahead excludes
# the Gemma-native <tool>{...} JSON form so it doesn't get misclassified as compliant.
OLLA_TOOL_RE = re.compile(r"<tool>(?!\s*\{)([^<]+)</tool>\s*<args>", re.IGNORECASE)

# olla's compliant <final> tag.
OLLA_FINAL_RE = re.compile(r"<final>", re.IGNORECASE)

FIXED_PROMPTS = [
    "List the files in the current directory.",
    "What is 2 + 2? Answer directly.",
]


def classify_response(content: str) -> str:
    """Three-way classify a model response for olla tag-format compliance (D-07)."""
    if OLLA_FINAL_RE.search(content) or OLLA_TOOL_RE.search(content):
        return "compliant"
    if NATIVE_QWEN_RE.search(content) or NATIVE_GEMMA_RE.search(content):
        return "reverted_to_native_format"
    return "non_compliant"


def run_smoke_test(model: str) -> None:
    """Run FIXED_PROMPTS against `model` under think=False and think=True,
    printing a per-think-mode tag-compliance summary (D-07/D-08)."""
    for think_mode in (False, True):
        results = {"compliant": 0, "reverted_to_native_format": 0, "non_compliant": 0}
        for prompt in FIXED_PROMPTS:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            content = call_model(model, messages, think=think_mode)
            results[classify_response(content)] += 1

        total = len(FIXED_PROMPTS)
        compliance_pct = results["compliant"] / total * 100
        print(
            f"{model} (think={think_mode}): {compliance_pct:.0f}% compliant "
            f"({results['compliant']}/{total}), "
            f"{results['reverted_to_native_format']} reverted to native format, "
            f"{results['non_compliant']} non-compliant"
        )
        if think_mode is False and compliance_pct < 80:
            print(
                f"  WARNING: {model} below 80% threshold (D-08) — flagged for follow-up, "
                f"no fallback format built"
            )
