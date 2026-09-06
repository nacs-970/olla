---
phase: 02-safety-gate-loop-control
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - src/olla/safety.py
  - tests/test_safety.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

This round (round 6) reviews plan 02-08's fix for CR-01 (round 5): `src/olla/safety.py` previously imported `typing.NotRequired`, a PEP 655 symbol added in Python 3.11, which broke `import olla.safety` on the declared `requires-python = ">=3.10"` floor. The fix changes `Decision` from `class Decision(TypedDict): ... reason: NotRequired[str]` to `class Decision(TypedDict, total=False): ... reason: str`, and adds two new tests: `test_safety_module_has_no_python311_only_typing_symbols` (a static source-text grep for `NotRequired`/`Required[`) and `test_decision_is_importable`.

**Verification performed:**
- Confirmed no remaining references to 3.11+-only typing symbols in `src/` (`grep -rn "NotRequired\|Required\[" src/` returns nothing).
- Ran the full test suite with `PYTHONPATH=src python3 -m pytest tests/test_safety.py -q` — all 64 tests pass.
- Traced both runtime accesses of `decision["reason"]` in `src/olla/loop.py` (lines 65, 111) — both are gated by `decision["kind"] == "BLOCK"`, and `check()` (`safety.py` lines 258, 262) always sets `reason` on the BLOCK return paths, so the `total=False` relaxation does not introduce a runtime `KeyError`.
- `str | None` (`safety.py:158`) is PEP 604 union syntax, valid on Python >=3.10 — no issue there.

The fix achieves its stated goal (restores 3.10 importability) with no behavior change to `check()`. CR-01 is resolved. However, the `total=False` approach taken is broader than necessary — it silently widens `kind` to optional as well as `reason`, when a narrower, equally 3.10-compatible pattern exists that preserves the original "kind always required" contract. Additionally, the new regression test that's supposed to *guarantee* portability is itself not portable due to a missing encoding argument on `open()`.

No critical/blocker issues found in this round.

## Warnings

### WR-01: `total=False` widens `kind` to optional too, when a narrower fix was available

**File:** `src/olla/safety.py:10-15`
**Issue:** The new `Decision` definition is:

```python
class Decision(TypedDict, total=False):
    kind: Literal["ALLOW", "CONFIRM", "BLOCK"]
    reason: str  # present only when kind == "BLOCK"; total=False is a
    # type-checker-only relaxation (no runtime enforcement either way) chosen
    # to avoid PEP 655's optional-key type marker (Python >=3.11 only) per
    # CR-01 -- check() always sets `kind` on every return path.
```

`total=False` applies to *every* field in the TypedDict, not just `reason`. Confirmed empirically:

```
>>> Decision.__required_keys__
frozenset()
>>> Decision.__optional_keys__
frozenset({'kind', 'reason'})
```

Before this fix, `kind` was a required key (enforced by static type checkers like mypy/pyright) and only `reason` was optional via `NotRequired[str]`. After this fix, `kind` is also optional at the type level. The comment frames this widening as a necessary "type-checker-only relaxation," but it isn't necessary — the pre-PEP-655 pattern for "base required fields + optional extension fields" is to split into a base class and an inheriting `total=False` class, which preserves the exact original contract and is compatible with Python >=3.10:

```python
class _DecisionBase(TypedDict):
    kind: Literal["ALLOW", "CONFIRM", "BLOCK"]


class Decision(_DecisionBase, total=False):
    reason: str  # present only when kind == "BLOCK"
```

This is purely a static-typing concern today (TypedDict performs no runtime enforcement either way, and `check()` does always set `kind`), so it does not cause a runtime bug right now. But it removes a type-checker safety net for free: with the current definition, a future code path in `check()` that forgets to set `kind` would type-check cleanly, and any `decision["kind"]` access in `loop.py` (e.g. lines 60, 62, 110) would then risk a runtime `KeyError` with no static warning.

**Fix:** Split `Decision` into a required base class plus a `total=False` extension, as shown above. This is a 3-line change, fully 3.10-compatible, and restores the original "kind required, reason optional" contract that `NotRequired[str]` provided.

### WR-02: New regression test uses `open()` without an encoding, making it non-portable across locales

**File:** `tests/test_safety.py:362-366`
**Issue:**
```python
def test_safety_module_has_no_python311_only_typing_symbols():
    source_path = inspect.getsourcefile(check)
    source = open(source_path).read()
    assert "NotRequired" not in source
    assert "Required[" not in source
```

`open(source_path)` with no `encoding=` argument uses `locale.getpreferredencoding(False)` to decode the file. `src/olla/safety.py` contains non-ASCII em-dash characters (U+2014, `—`, 8 occurrences in comments, e.g. lines 18, 37, 47, 58, 62, 73, 76, 79). Verified empirically: under a non-UTF-8 locale (`LC_ALL=C`) with `PYTHONUTF8=0` — a realistic configuration for minimal containers/CI runners, which is exactly the kind of constrained environment a "Python 3.10 portability" regression test should be robust against — this `open(source_path).read()` raises:

```
UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 579: ordinal not in range(128)
```

This means the CR-01 portability regression test can itself fail with an unrelated `UnicodeDecodeError` on systems where it matters most (minimal/locale-restricted environments), masking the actual NotRequired/Required[ check it exists to perform. This is a test-reliability defect: a spurious failure here would be confusing (it looks like a collection error, not "safety.py imports NotRequired").

**Fix:** Specify UTF-8 explicitly, since that's the actual encoding of the source file:

```python
def test_safety_module_has_no_python311_only_typing_symbols():
    source_path = inspect.getsourcefile(check)
    with open(source_path, encoding="utf-8") as f:
        source = f.read()
    assert "NotRequired" not in source
    assert "Required[" not in source
```

(Also addresses the unrelated minor issue of not closing the file handle via `with`.)

## Info

### IN-01: `test_decision_is_importable` cannot fail independently of module collection

**File:** `tests/test_safety.py:369-373`
**Issue:**
```python
def test_decision_is_importable():
    # Confirms the Decision TypedDict is still exported after the
    # `class Decision(TypedDict, total=False):` rename (CR-01).
    assert Decision is not None
```

`Decision` is imported at module scope (`tests/test_safety.py:5`, `from olla.safety import ALLOWLIST, Decision, check`). If that import failed (e.g. `Decision` were removed or renamed), the entire test module would fail at collection time with an `ImportError`/`ModuleNotFoundError`, before any individual test — including this one — runs. `TypedDict` classes are also never `None` once successfully imported (`Decision is not None` is trivially true for any class object). So this test cannot meaningfully fail on its own; it's effectively a no-op that piggybacks on collection-time import success.

**Fix:** This is low-cost and harmless as a documentation-style sanity check, so it's fine to leave as-is. If a more meaningful assertion is wanted, consider checking the TypedDict's shape directly, e.g.:

```python
def test_decision_has_expected_keys():
    assert Decision.__annotations__.keys() == {"kind", "reason"}
```

### IN-02: Test name claims to check for "Python 3.11-only typing symbols" generally, but only checks two specific symbols

**File:** `tests/test_safety.py:362-366`
**Issue:** The test name `test_safety_module_has_no_python311_only_typing_symbols` and its docstring-comment block (lines 346-361) frame this as a general guard against any Python-3.11+-only typing symbol leaking into `safety.py`. The actual assertions only check for the two PEP 655 symbols (`NotRequired`, `Required[`) that caused this specific CR-01 regression. Other 3.11+-only typing additions (e.g. `typing.Self`, `typing.assert_type`, `typing.dataclass_transform`, `typing.Unpack`) would not be caught by this test despite the name's implication of broader coverage.
**Fix:** Either narrow the name/docstring to be explicit about scope (e.g. `test_safety_module_has_no_pep655_notrequired_or_required`), or broaden the check to a small list of known 3.11+-only `typing` symbols if more general protection is desired. Given this is a targeted regression test for a specific incident (CR-01), a scope-clarifying rename is the lower-risk option and keeps the test's claims accurate.

---

_Reviewed: 2026-06-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
