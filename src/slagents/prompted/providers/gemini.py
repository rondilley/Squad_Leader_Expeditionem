"""The Google Gemini adapter (IR-02, FR-62).

The Generative Language API is neither the OpenAI shape nor the Anthropic shape, so it gets
its own adapter. Three things differ:

- The model is part of the path, not a field of the payload: `/models/<model>:generateContent`.
- The system prompt is `system_instruction`, and the user turn is a list of parts.
- The schema goes in `generationConfig.responseSchema`, next to a response type of
  `application/json`. That is real constrained decoding, so this adapter says yes to
  `supports_constraint` and FR-62 holds on it.

The schema field takes a subset of JSON Schema. It has no `additionalProperties` and no
`$schema`, and `propertyOrdering` decides the order of the fields in the answer. So the
adapter translates the project schema into that subset instead of sending it as it stands.

The health check calls `/models`, which lists what the key can reach and spends no tokens.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from slagents.prompted import keys
from slagents.prompted.providers.base import (
    Answer,
    Provider,
    ProviderError,
    ProviderUnavailable,
)

KEY_HEADER = "x-goog-api-key"
MODELS_PATH = "/models"
# The keys of JSON Schema that the response schema of this API does not take.
UNSUPPORTED = ("additionalProperties", "$schema", "definitions", "$defs", "title")


def to_response_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """The project schema in the subset that `responseSchema` takes.

    The keys this API refuses go away, and the order of the properties comes with the
    object, so that the answer reads the way the prompt asks for it.
    """
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in UNSUPPORTED:
            continue
        if key == "properties" and isinstance(value, Mapping):
            out["properties"] = {k: to_response_schema(v) for k, v in value.items()}
            out["propertyOrdering"] = list(value)
        elif key == "items" and isinstance(value, Mapping):
            out["items"] = to_response_schema(value)
        else:
            out[key] = value
    return out


class GeminiProvider(Provider):
    """One turn over the Generative Language API."""

    def headers(self) -> dict[str, str]:
        name = self.config.key or "gemini"
        try:
            return {KEY_HEADER: keys.load(name)}
        except keys.KeyMissing as exc:
            raise ProviderUnavailable(str(exc)) from exc

    def health(self) -> bool:
        """The model list. It needs the key, it spends no tokens, and it names the models."""
        if not keys.available(self.config.key or "gemini"):
            return False
        try:
            document = self.get_with_key(self.config.health or MODELS_PATH)
        except ProviderError:
            return False
        return bool(document.get("models"))

    def get_with_key(self, path: str) -> dict[str, Any]:
        """A GET with the key header. The base class GET carries no headers."""
        import urllib.request

        request = urllib.request.Request(self.url(path), method="GET")
        request.add_header("User-Agent", "squad-leader-ai/0.1 (+local research build)")
        for key, value in self.headers().items():
            request.add_header(key, value)
        return self._send(request)

    def supports_constraint(self) -> bool:
        return True

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 700,
        temperature: float = 0.2,
        json_schema: Mapping[str, Any] | None = None,
    ) -> Answer:
        # A 2.5 model thinks before it answers, and the thinking comes out of the same
        # output budget. With the budget of this harness the thinking ate the answer and
        # the call came back at MAX_TOKENS with no text, so the budget is zero here. The
        # harness asks for one command from a list it already has, and that is a choice
        # and not a problem to think about.
        generation: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
        }
        if json_schema is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = to_response_schema(json_schema)
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation,
        }
        started = time.perf_counter()
        document = self.post(f"{MODELS_PATH}/{self.config.model}:generateContent", payload, self.headers())
        seconds = time.perf_counter() - started
        candidates = document.get("candidates") or []
        if not candidates:
            reason = (document.get("promptFeedback") or {}).get("blockReason") or "no candidate"
            raise ProviderError(f"{self.name} gave no answer: {reason}")
        first = candidates[0]
        parts = ((first.get("content") or {}).get("parts")) or []
        text = "".join(str(part.get("text") or "") for part in parts)
        if not text:
            raise ProviderError(f"{self.name} gave no text in its answer")
        usage = document.get("usageMetadata") or {}
        return Answer(
            text=text,
            seconds=seconds,
            provider=self.name,
            model=str(document.get("modelVersion") or self.config.model),
            tokens_in=int(usage.get("promptTokenCount") or 0),
            tokens_out=int(usage.get("candidatesTokenCount") or 0),
            finish_reason=str(first.get("finishReason") or ""),
        )
