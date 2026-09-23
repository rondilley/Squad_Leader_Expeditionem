"""The adapter for an OpenAI-compatible endpoint (IR-01).

The local llama-server speaks this API, and so do several of the SaaS providers. One
adapter covers them, and the difference between them is one row of the configuration file.

The health check is a real call to `/models` at start, which is what IR-01 asks for. A
provider that does not answer that call is unavailable, and the harness moves to the next
one (IR-05).
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from slagents.prompted import keys
from slagents.prompted.providers.base import Answer, Provider, ProviderError, ProviderUnavailable

CHAT_PATH = "/chat/completions"
DEFAULT_HEALTH = "/models"


class OpenAiCompatibleProvider(Provider):
    """Chat completions over the OpenAI-compatible HTTP API."""

    def headers(self) -> dict[str, str]:
        if self.config.key is None:
            return {}
        try:
            return {"Authorization": f"Bearer {keys.load(self.config.key)}"}
        except keys.KeyMissing as exc:
            raise ProviderUnavailable(str(exc)) from exc

    def health(self) -> bool:
        """IR-01: a real call to the models endpoint at start."""
        path = self.config.health or DEFAULT_HEALTH
        try:
            document = self.get(path) if not self.config.key else self._get_with_key(path)
        except ProviderUnavailable:
            return False
        except ProviderError:
            return False
        return isinstance(document, dict) and ("data" in document or "models" in document)

    def _get_with_key(self, path: str) -> dict[str, Any]:
        import urllib.request

        request = urllib.request.Request(self.url(path), method="GET")
        for key, value in self.headers().items():
            request.add_header(key, value)
        return self._send(request)

    def supports_constraint(self) -> bool:
        """FR-62: this API takes a JSON schema, and llama-server takes the same field."""
        return True

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 700,
        temperature: float = 0.2,
        json_schema: Mapping[str, Any] | None = None,
    ) -> Answer:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            **self.config.request_fields(),
        }
        if json_schema is not None:
            # FR-62: the legal identities are the enum of the command field, so a model
            # under this constraint cannot name a command that is not legal.
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "move", "schema": dict(json_schema), "strict": True},
            }
        started = time.perf_counter()
        document = self.post(CHAT_PATH, payload, self.headers())
        seconds = time.perf_counter() - started
        choices = document.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.name} gave no choice in its answer")
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "")
        usage = document.get("usage") or {}
        return Answer(
            text=text,
            seconds=seconds,
            provider=self.name,
            model=str(document.get("model") or self.config.model),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            finish_reason=str(choices[0].get("finish_reason") or ""),
        )
