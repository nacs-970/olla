"""CLI entry point wiring TASK + flags to the ReAct loop."""

import click

from olla.config import load_config
from olla.loop import run_loop
from olla.prompts import SYSTEM_PROMPT
from olla.smoke import run_smoke_test


@click.command()
@click.argument("task", required=False)
@click.option(
    "--model",
    required=False,
    default=None,
    help="Model identifier (e.g. qwen2.5:3b or openrouter/meta-llama/llama-3.1-8b)",
)
@click.option("--dry-run", is_flag=True)
@click.option("--max-steps", default=15, show_default=True, type=int)
@click.option("--yes", is_flag=True)
@click.option("--smoke-test", is_flag=True, help="Run format-compliance check against --model")
@click.option("--api-key", required=False, default=None, help="API key for remote model provider")
@click.option("--base-url", required=False, default=None, help="Custom base URL for OpenAI-compatible API")
def main(task, model, dry_run, max_steps, yes, smoke_test, api_key, base_url):
    """Run an agentic task against a local or remote model."""
    cfg = load_config()
    model = model or cfg.get("default_model") or cfg.get("model")
    api_key = api_key or cfg.get("api_key")
    base_url = base_url or cfg.get("base_url")

    if smoke_test:
        if not model:
            raise click.UsageError("--smoke-test requires --model")
        run_smoke_test(model, api_key=api_key, base_url=base_url)
        return

    if not task:
        raise click.UsageError("TASK argument is required")
    if not model:
        raise click.UsageError("--model is required (no hardcoded default model, CLI-01)")

    run_loop(
        task=task,
        model=model,
        max_steps=max_steps,
        system_prompt=SYSTEM_PROMPT,
        yes=yes,
        dry_run=dry_run,
        api_key=api_key,
        base_url=base_url,
    )
