"""The Anthropic adapter (IR-02).

The one SaaS adapter of v0.4. Its message API differs from the OpenAI-compatible one in
three places: the system prompt is its own field, the key goes in an `x-api-key` header,
and the answer holds a list of content blocks.

The health check does not call the network. Anthropic has no free endpoint that says
"this key works", and a call that spends tokens is not a health check. So the check is the
key: a provider with a key is available, and a call that fails says why (IR-05).
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from slagents.prompted import keys
from slagents.prompted.providers.base import Answer, Provider, ProviderError, ProviderUnavailable

MESSAGES_PATH = "/messages"
DEFAULT_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    """Messages over the Anthropic HTTP API."""

    def headers(self) -> dict[str, str]:
        name = self.config.key or "claude"
        try:
            return {
                "x-api-key": keys.load(name),
                "anthropic-version": self.config.version or DEFAULT_VERSION,
            }
        except keys.KeyMissing as exc:
            raise ProviderUnavailable(str(exc)) from exc

    def health(self) -> bool:
        """A key on the machine. A call that spends tokens is not a health check."""
        return keys.available(self.config.key or "claude")

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 700,
        temperature: float = 0.2,
        json_schema: Mapping[str, Any] | None = None,
    ) -> Answer:
        # This API has no schema field on a plain message, so the schema stays in the
        # prompt and `supports_constraint` says so (FR-62).
        payload = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        started = time.perf_counter()
        document = self.post(MESSAGES_PATH, payload, self.headers())
        seconds = time.perf_counter() - started
        blocks = document.get("content") or []
        text = "".join(str(block.get("text") or "") for block in blocks if block.get("type") == "text")
        if not text:
            raise ProviderError(f"{self.name} gave no text in its answer")
        usage = document.get("usage") or {}
        return Answer(
            text=text,
            seconds=seconds,
            provider=self.name,
            model=str(document.get("model") or self.config.model),
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
            finish_reason=str(document.get("stop_reason") or ""),
        )
