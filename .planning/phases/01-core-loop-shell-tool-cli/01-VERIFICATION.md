---
phase: 01-core-loop-shell-tool-cli
verified: 2026-09-07T03:44:00Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
---

# Phase 1: Core Loop + Shell Tool + CLI Verification Report

**Phase Goal:** As a user running an agentic task with olla, I want to drive shell commands to completion with local Ollama models in a ReAct loop, so that the tag-format contract is validated against target models.
**Verified:** 2026-09-07T03:44:00Z
**Status:** passed

## Goal Achievement

### Observable Truths

| # | Roadmap Success Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `olla "task description" --model <name>` drives shell command to `<final>` answer without hardcoded default model | ✓ VERIFIED | `tests/test_cli.py::test_task_and_model_call_run_loop_with_defaults` |
| 2 | Parser extracts `<tool>`/`<args>`/`<final>` from model output even wrapped in markdown fences, surrounding prose, or unclosed tags | ✓ VERIFIED | `tests/test_parser.py` (44 passing tests) |
| 3 | Model stops generating at tool-call boundary (stop-sequence) and large output is truncated | ✓ VERIFIED | `tests/test_loop.py::test_run_loop_read_file_truncates_large_output` |
| 4 | Each step prints visible progress ("Step N: running `<cmd>`...") as loop executes | ✓ VERIFIED | `tests/test_loop.py::test_run_loop_allow_tier_no_prompt` |
| 5 | `pip install` exposes `olla` console-script on PATH | ✓ VERIFIED | `pyproject.toml` defines `[project.scripts] olla = "olla.cli:main"` |
| 6 | Format-validation smoke test reports tag-compliance rates for models | ✓ VERIFIED | `tests/test_smoke.py` (10 passing tests) |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/olla/cli.py` | CLI entry point wiring args to loop | ✓ EXISTS + SUBSTANTIVE | Entrypoint handling flags, config, providers |
| `src/olla/loop.py` | ReAct loop driving reasoning and tools | ✓ EXISTS + SUBSTANTIVE | Core execution loop |
| `src/olla/parser.py` | Tolerant tag parser | ✓ EXISTS + SUBSTANTIVE | Extracts tool, args, final tags |
| `src/olla/tools/shell.py` | Subprocess shell tool runner | ✓ EXISTS + SUBSTANTIVE | Executes shell commands safely |
| `src/olla/smoke.py` | Model compliance smoke tester | ✓ EXISTS + SUBSTANTIVE | Runs multi-prompt compliance checks |

**Artifacts:** 5/5 verified

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|---|---|---|---|
| LOOP-01 | ReAct loop tag parsing | ✓ SATISFIED | Full parser test suite passing |
| LOOP-02 | Stop sequences passed to chat | ✓ SATISFIED | Stop sequences configured in chat calls |
| LOOP-03 | Explicit num_ctx and truncation | ✓ SATISFIED | Output truncation enforced |
| LOOP-05 | Visible step progress | ✓ SATISFIED | Step progress displayed during execution |
| SHELL-01 | Subprocess shell runner (shell=False) | ✓ SATISFIED | `tests/test_tools/test_shell.py` passing |
| CLI-01 | --model flag required, no default | ✓ SATISFIED | `tests/test_cli.py` passing |
| CLI-02 | One-shot task completion | ✓ SATISFIED | End-to-end task execution passing |
| CLI-03 | Pip-installable console-script | ✓ SATISFIED | `pyproject.toml` console script defined |

## Result

Status: **passed**  
Phase 1 Core Loop + Shell Tool + CLI goal fully achieved and verified against all contracts.

