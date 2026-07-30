<!-- generated-by: gsd-doc-writer -->
# olla

`olla` is a lightweight Python CLI for running agentic shell and file tasks with local Ollama models, designed to stay responsive with small models and constrained hardware.

> **Work in progress:** This project is under active development, so features and behavior may change.

## Requirements

- Python `>=3.10`
- A running Ollama installation with at least one local model available

## Installation

Install from the repository with `pip`:

```bash
git clone git@github.com:nacs-970/olla.git
cd olla
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

For local development, install the optional test and lint dependencies instead:

```bash
python -m pip install -e ".[dev]"
```

## Quick start

1. Make sure Ollama is running and note the name of a model installed locally.

2. Run a task, replacing `your-model-name` with that model's name:

   ```bash
   olla "What is 2 + 2? Answer directly." --model your-model-name
   ```

3. Read the final answer printed to the terminal. `olla` may perform intermediate tool calls before it answers.

There is no default model: every task must include `--model`.

## Usage examples

Ask the model to inspect the current directory:

```bash
olla "List the Python files in the current directory." --model your-model-name
```

Read-only commands such as `ls`, `pwd`, and `grep` can run automatically. The CLI prints each tool step and then the model's final answer.

Preview the first proposed action without executing it:

```bash
olla "Create notes.txt containing today's priorities." \
  --model your-model-name \
  --dry-run
```

The result describes what the model would do, including whether a shell command would be allowed, confirmed, or blocked. No tool action is executed.

Check whether a model follows `olla`'s tool-call format:

```bash
olla --smoke-test --model your-model-name
```

The smoke test reports compliance percentages for both `think=False` and `think=True` responses.

Useful options:

- `--max-steps INTEGER` changes the loop limit from its default of 15 steps.
- `--yes` automatically approves actions that would normally ask for confirmation; hard-blocked commands remain blocked.
- `--dry-run` requests one model response and previews that action without running it.
- `--smoke-test` runs the model format-compliance check and does not require a task argument.

## Safety

`olla` can execute model-proposed commands and write files. Commands are parsed into argument lists and run without a shell. Known destructive operations are blocked, while non-read-only commands and file writes require confirmation unless `--yes` is supplied. Before overwriting an existing file, the model must read its complete contents during the same run, and the write is refused if the file changes before replacement.

Use `--dry-run` when you want to inspect a model's first proposed action before allowing tool execution.

## License

This repository does not currently declare a license.
