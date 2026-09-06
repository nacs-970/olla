"""OpenAI-compatible streaming provider implementation with stop sequence buffering."""

import json
import time
from collections.abc import Iterator

import httpx

from olla.providers.base import ProviderError, StreamChunk


def stream_with_stop_buffer(
    iterator: Iterator[StreamChunk], stop_seq: str = "</args>"
) -> Iterator[StreamChunk]:
    """Stream chunks while buffering trailing text to prevent stop_seq from leaking.

    Halts immediately when stop_seq is encountered.
    """
    buffer = ""
    stop_len = len(stop_seq)

    for chunk in iterator:
        if chunk.is_thought:
            # Flush non-thought buffer if any before yielding thought
            if buffer:
                yield StreamChunk(text=buffer, is_thought=False)
                buffer = ""
            yield chunk
            continue

        buffer += chunk.text

        # Check if full stop sequence is in the buffer
        stop_idx = buffer.find(stop_seq)
        if stop_idx != -1:
            # Emit everything up to stop_seq, then terminate stream
            before = buffer[:stop_idx]
            if before:
                yield StreamChunk(text=before, is_thought=False)
            return

        # Find longest prefix of stop_seq that matches suffix of buffer
        match_len = 0
        max_possible = min(len(buffer), stop_len - 1)
        for length in range(max_possible, 0, -1):
            if buffer.endswith(stop_seq[:length]):
                match_len = length
                break

        # Yield safe portion before potential stop sequence prefix
        if match_len > 0:
            safe_text = buffer[:-match_len]
            buffer = buffer[-match_len:]
        else:
            safe_text = buffer
            buffer = ""

        if safe_text:
            yield StreamChunk(text=safe_text, is_thought=False)

    # Flush remaining buffer at end of stream if stop_seq was never matched
    if buffer:
        yield StreamChunk(text=buffer, is_thought=False)


class OpenAICompatProvider:
    """Provider for OpenAI-compatible APIs (OpenRouter, OpenAI, vLLM, etc.)."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._context_length: int | None = None

    def get_context_length(self) -> int:
        """Return context length for model, fetching dynamically if possible."""
        if self._context_length is not None:
            return self._context_length

        try:
            with httpx.Client(timeout=5.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                resp = client.get(f"{self.base_url}/models", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models_list = data.get("data", [])
                    for m in models_list:
                        if m.get("id") == self.model and "context_length" in m:
                            self._context_length = int(m["context_length"])
                            return self._context_length
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
            self._context_length = 128000
            return self._context_length

        self._context_length = 128000
        return self._context_length

    def _raw_stream_request(self, messages: list[dict]) -> Iterator[StreamChunk]:
        """Execute streaming HTTP request with retries and parse SSE chunks."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/olla/olla",
            "X-Title": "olla CLI Agent",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "stop": ["</args>"],
            "stream": True,
        }

        backoff_delays = [1.0, 2.0, 4.0]
        max_attempts = len(backoff_delays) + 1
        last_exception: Exception | None = None

        for attempt in range(max_attempts):
            try:
                with (
                    httpx.Client(timeout=self.timeout) as client,
                    client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response,
                ):
                        if response.status_code in (429, 500, 502, 503, 504):
                            error_body = response.read().decode("utf-8", errors="replace")
                            if attempt < len(backoff_delays):
                                time.sleep(backoff_delays[attempt])
                                continue
                            raise ProviderError(
                                f"API error ({response.status_code}) after retries: {error_body}"
                            )

                        if response.status_code != 200:
                            error_body = response.read().decode("utf-8", errors="replace")
                            raise ProviderError(
                                f"API error ({response.status_code}): {error_body}"
                            )

                        in_think_tag = False
                        for line in response.iter_lines():
                            line = line.strip()
                            if not line or line.startswith(":"):
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                            elif line == "data:":
                                continue
                            else:
                                continue

                            if data_str == "[DONE]":
                                break

                            try:
                                chunk_json = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            choices = chunk_json.get("choices") or []
                            if not choices:
                                continue

                            delta = choices[0].get("delta", {})

                            # Handle explicit reasoning / reasoning_content field
                            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                            if reasoning:
                                yield StreamChunk(text=reasoning, is_thought=True)

                            content = delta.get("content")
                            if content:
                                # Handle inline <think>...</think> tags if model emits them in content
                                remaining = content
                                while remaining:
                                    if not in_think_tag:
                                        think_start = remaining.find("<think>")
                                        if think_start != -1:
                                            before = remaining[:think_start]
                                            if before:
                                                yield StreamChunk(text=before, is_thought=False)
                                            in_think_tag = True
                                            remaining = remaining[think_start + len("<think>"):]
                                        else:
                                            yield StreamChunk(text=remaining, is_thought=False)
                                            break
                                    else:
                                        think_end = remaining.find("</think>")
                                        if think_end != -1:
                                            thought_text = remaining[:think_end]
                                            if thought_text:
                                                yield StreamChunk(text=thought_text, is_thought=True)
                                            in_think_tag = False
                                            remaining = remaining[think_end + len("</think>"):]
                                        else:
                                            yield StreamChunk(text=remaining, is_thought=True)
                                            break
                        return
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exception = exc
                if attempt < len(backoff_delays):
                    time.sleep(backoff_delays[attempt])
                    continue
                raise ProviderError(f"Connection failed after retries: {exc}") from exc

        if last_exception:
            raise ProviderError(f"Request failed: {last_exception}") from last_exception

    def stream_chat(self, messages: list[dict], think: bool = False) -> Iterator[StreamChunk]:
        """Stream chunks, applying stop sequence buffering to avoid leaking </args>."""
        raw_stream = self._raw_stream_request(messages)
        return stream_with_stop_buffer(raw_stream, stop_seq="</args>")

    def chat(self, messages: list[dict], think: bool = False) -> str:
        """Execute chat request synchronously by accumulating stream output."""
        output_parts: list[str] = []
        for chunk in self.stream_chat(messages, think=think):
            if not chunk.is_thought:
                output_parts.append(chunk.text)
        return "".join(output_parts)
