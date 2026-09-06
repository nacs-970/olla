import os

from olla.config import load_config
from olla.providers.base import Provider, ProviderError, StreamChunk
from olla.providers.ollama import OllamaProvider
from olla.providers.openai_compat import OpenAICompatProvider, stream_with_stop_buffer


def get_provider(
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 60.0,
) -> tuple[Provider, str]:
    """Factory routing a model identifier to its corresponding Provider instance.

    Returns:
        tuple[Provider, str]: The instantiated provider and the stripped model identifier.
    """
    cfg = load_config()

    if model.startswith("openrouter/"):
        model_id = model[len("openrouter/"):]
        router_cfg = cfg.get("openrouter") if isinstance(cfg.get("openrouter"), dict) else {}
        effective_base_url = (
            base_url
            or os.environ.get("OPENROUTER_BASE_URL")
            or router_cfg.get("base_url")
            or cfg.get("openrouter_base_url")
            or cfg.get("base_url")
            or "https://openrouter.ai/api/v1"
        )
        effective_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or router_cfg.get("api_key")
            or cfg.get("openrouter_api_key")
            or cfg.get("api_key")
        )
        if not effective_key:
            raise ProviderError(
                "Missing API key for remote model. Set OPENROUTER_API_KEY, pass --api-key, or set in config.toml."
            )
        return (
            OpenAICompatProvider(
                model=model_id,
                api_key=effective_key,
                base_url=effective_base_url,
                timeout=timeout,
            ),
            model_id,
        )

    if model.startswith("openai/"):
        model_id = model[len("openai/"):]
        openai_cfg = cfg.get("openai") if isinstance(cfg.get("openai"), dict) else {}
        effective_base_url = (
            base_url
            or os.environ.get("OPENAI_BASE_URL")
            or openai_cfg.get("base_url")
            or cfg.get("openai_base_url")
            or cfg.get("base_url")
            or "https://api.openai.com/v1"
        )
        effective_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or openai_cfg.get("api_key")
            or cfg.get("openai_api_key")
            or cfg.get("api_key")
        )
        if not effective_key:
            raise ProviderError(
                "Missing API key for remote model. Set OPENAI_API_KEY, pass --api-key, or set in config.toml."
            )
        return (
            OpenAICompatProvider(
                model=model_id,
                api_key=effective_key,
                base_url=effective_base_url,
                timeout=timeout,
            ),
            model_id,
        )

    if model.startswith("ollama/"):
        model_id = model[len("ollama/"):]
        return OllamaProvider(model=model_id), model_id

    # Unprefixed model defaults to local Ollama
    return OllamaProvider(model=model), model


__all__ = [
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "ProviderError",
    "StreamChunk",
    "get_provider",
    "stream_with_stop_buffer",
]
