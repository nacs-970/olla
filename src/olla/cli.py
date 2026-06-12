"""CLI entry point wiring TASK + flags to the ReAct loop."""

import click

from olla.loop import run_loop
from olla.prompts import SYSTEM_PROMPT
from olla.smoke import run_smoke_test


@click.command()
@click.argument("task", required=False)
@click.option("--model", required=False, default=None, help="Ollama model name (no default)")
@click.option("--dry-run", is_flag=True)
@click.option("--max-steps", default=15, show_default=True, type=int)
@click.option("--yes", is_flag=True)
@click.option("--smoke-test", is_flag=True, help="Run format-compliance check against --model")
def main(task, model, dry_run, max_steps, yes, smoke_test):
    """Run an agentic task against a local Ollama model."""
    if smoke_test:
        if not model:
            raise click.UsageError("--smoke-test requires --model")
        run_smoke_test(model)
        return

    if not task:
        raise click.UsageError("TASK argument is required")
    if not model:
        raise click.UsageError("--model is required (no hardcoded default model, CLI-01)")

    run_loop(task=task, model=model, max_steps=max_steps, system_prompt=SYSTEM_PROMPT, yes=yes, dry_run=dry_run)
