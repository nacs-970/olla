"""Base provider protocol, chunk types, and errors."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    """Clean diagnostic exception for provider failures."""


@dataclass
class StreamChunk:
    """A streaming text chunk with optional reasoning/thought tag."""

    text: str
    is_thought: bool = False


class Provider(Protocol):
    """Unified LLM provider interface."""

    def chat(self, messages: list[dict], think: bool = False) -> str:
        """Complete a chat request synchronously."""
        ...

    def stream_chat(self, messages: list[dict], think: bool = False) -> Iterator[StreamChunk]:
        """Stream response chunks synchronously."""
        ...

    def get_context_length(self) -> int:
        """Return maximum context window size in tokens."""
        ...
