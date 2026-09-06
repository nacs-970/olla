"""Ollama local model provider implementation."""

from collections.abc import Iterator

import ollama

from olla.providers.base import ProviderError, StreamChunk


class OllamaProvider:
    """Provider for local Ollama models."""

    def __init__(self, model: str, num_ctx: int = 8192) -> None:
        self.model = model
        self.num_ctx = num_ctx

    def get_context_length(self) -> int:
        """Return configured context length."""
        return self.num_ctx

    def chat(self, messages: list[dict], think: bool = False) -> str:
        """Execute non-streaming chat request with Ollama."""
        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={"stop": ["</args>"], "num_ctx": self.num_ctx},
                think=think,
            )
            message = response.get("message") if isinstance(response, dict) else getattr(response, "message", None)
            if message is None:
                return ""
            content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
            return content or ""
        except (ollama.RequestError, ollama.ResponseError) as error:
            raise ProviderError(f"Ollama request failed for model '{self.model}': {error}") from error
        except Exception as error:
            raise ProviderError(f"Unexpected Ollama error for model '{self.model}': {error}") from error

    def stream_chat(self, messages: list[dict], think: bool = False) -> Iterator[StreamChunk]:
        """Stream chat chunks from Ollama."""
        try:
            stream = ollama.chat(
                model=self.model,
                messages=messages,
                options={"stop": ["</args>"], "num_ctx": self.num_ctx},
                think=think,
                stream=True,
            )
            for chunk in stream:
                message = chunk.get("message") if isinstance(chunk, dict) else getattr(chunk, "message", None)
                if message is None:
                    continue
                content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
                if content:
                    yield StreamChunk(text=content, is_thought=False)
        except (ollama.RequestError, ollama.ResponseError) as error:
            raise ProviderError(f"Ollama stream failed for model '{self.model}': {error}") from error
        except Exception as error:
            raise ProviderError(f"Unexpected Ollama stream error for model '{self.model}': {error}") from error
