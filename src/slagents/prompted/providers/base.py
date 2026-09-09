"""The provider interface and the host allowlist (IR-02, SR-05).

One interface, one thin adapter for each provider. The interface has three members:

- `health()` says whether the provider answers at all. The local endpoint does a real
  call to `/v1/models` (IR-01), and a SaaS provider reports whether its key is present.
- `complete(system, user)` sends the two parts of the prompt and gives back the text, the
  time it took, and what the provider said about the tokens.
- `name` and `model` identify it in a run artifact.

The allowlist is the security boundary of SR-05. A request goes to a host in
`sldata/providers.json` and to no other host. No user interface, no scenario file, and no
model answer can name an address, because the address never comes from any of them.

The adapters use `urllib` from the standard library. The project has one runtime
dependency, and one HTTP POST does not need a second.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping

from slagents.prompted import keys
from sldata.loaders import DataError, read_data

PROVIDERS_FILE = "providers.json"
USER_AGENT = "squad-leader-ai/0.1 (+local research build)"


class ProviderError(Exception):
    """A provider call did not give an answer. The message never holds a key."""


class ProviderUnavailable(ProviderError):
    """The provider has no key, or its endpoint does not answer."""


@dataclass(frozen=True)
class Answer:
    """What one call gave back."""

    text: str
    seconds: float
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    finish_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "seconds": round(self.seconds, 3),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "finish_reason": self.finish_reason,
            "characters": len(self.text),
        }


@dataclass(frozen=True)
class ProviderConfig:
    """One row of the provider configuration."""

    name: str
    kind: str
    endpoint: str
    model: str
    key: str | None = None
    health: str = ""
    version: str = ""
    timeout_seconds: float = 90.0
    tier: str = "rc"

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "ProviderConfig":
        return ProviderConfig(
            name=str(d["name"]),
            kind=str(d["kind"]),
            endpoint=str(d["endpoint"]),
            model=str(d["model"]),
            key=None if d.get("key") is None else str(d["key"]),
            health=str(d.get("health", "")),
            version=str(d.get("version", "")),
            timeout_seconds=float(d.get("timeout_seconds", 90.0)),
            tier=str(d.get("tier", "rc")),
        )


@dataclass
class Config:
    """The whole provider configuration: the allowlist and the rows."""

    allowlist: tuple[str, ...]
    providers: tuple[ProviderConfig, ...]

    def by_name(self, name: str) -> ProviderConfig:
        for row in self.providers:
            if row.name == name:
                return row
        raise ProviderError(f"there is no provider named {name!r} in {PROVIDERS_FILE}")


def load_config() -> Config:
    """The provider configuration from the data file, and from no other place (SR-05)."""
    document = read_data(PROVIDERS_FILE)
    return Config(
        allowlist=tuple(str(x) for x in document.get("allowlist", [])),
        providers=tuple(ProviderConfig.from_dict(row) for row in document.get("providers", [])),
    )


def allowed_host(url: str, allowlist: tuple[str, ...]) -> bool:
    """SR-05: the scheme and the host of a request must be on the allowlist."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    origin = f"{parts.scheme}://{parts.netloc}"
    return origin in allowlist


class Provider:
    """The interface. An adapter fills in `complete` and `health`."""

    def __init__(self, config: ProviderConfig, allowlist: tuple[str, ...]) -> None:
        if not allowed_host(config.endpoint, allowlist):
            raise ProviderError(
                f"the endpoint of {config.name} is not on the allowlist of {PROVIDERS_FILE} (SR-05)"
            )
        self.config = config
        self.allowlist = allowlist

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    def health(self) -> bool:
        raise NotImplementedError(f"the provider kind {self.config.kind!r} has no health check")

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 700,
        temperature: float = 0.2,
        json_schema: Mapping[str, Any] | None = None,
    ) -> Answer:
        """One call. With a schema, the provider constrains the answer to it (FR-62)."""
        raise NotImplementedError(f"the provider kind {self.config.kind!r} waits for its adapter")

    def supports_constraint(self) -> bool:
        """Whether this adapter can hold the model to a schema (FR-62)."""
        return False

    # ------------------------------------------------------------- the wire

    def post(self, path: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        url = self.url(path)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("User-Agent", USER_AGENT)
        for key, value in headers.items():
            request.add_header(key, value)
        return self._send(request)

    def get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(self.url(path), method="GET")
        request.add_header("User-Agent", USER_AGENT)
        return self._send(request)

    def url(self, path: str) -> str:
        url = f"{self.config.endpoint.rstrip('/')}/{path.lstrip('/')}"
        if not allowed_host(url, self.allowlist):
            raise ProviderError(f"the address {url} is not on the allowlist (SR-05)")
        return url

    def _send(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as answer:
                raw = answer.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300] if exc.fp else ""
            raise ProviderError(f"{self.name} answered {exc.code}: {self._safe(detail)}") from exc
        except urllib.error.URLError as exc:
            raise ProviderUnavailable(f"{self.name} did not answer: {self._safe(str(exc.reason))}") from exc
        except TimeoutError as exc:
            raise ProviderUnavailable(f"{self.name} did not answer inside {self.config.timeout_seconds} s") from exc
        except OSError as exc:
            # A server that closes the connection, or a network that goes away. The local
            # endpoint does both while it loads a model, so this is a state and not a fault.
            raise ProviderUnavailable(f"{self.name} closed the connection: {self._safe(str(exc))}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.name} gave an answer that is not JSON: {self._safe(raw[:200])}") from exc

    def _safe(self, text: str) -> str:
        """No message from this module holds a key (SR-01)."""
        return keys.redact(text, self.config.key) if self.config.key else text


def make_provider(name: str, config: Config | None = None) -> Provider:
    """One provider by name, with the adapter of its kind."""
    from slagents.prompted.providers.anthropic import AnthropicProvider
    from slagents.prompted.providers.gemini import GeminiProvider
    from slagents.prompted.providers.openai_compatible import OpenAiCompatibleProvider

    settings = config or load_config()
    row = settings.by_name(name)
    if row.kind == "openai_compatible":
        return OpenAiCompatibleProvider(row, settings.allowlist)
    if row.kind == "anthropic":
        return AnthropicProvider(row, settings.allowlist)
    if row.kind == "gemini":
        return GeminiProvider(row, settings.allowlist)
    raise ProviderError(f"the provider kind {row.kind!r} has no adapter in this build")


def providers_for(tier: str, config: Config | None = None) -> list[str]:
    """The providers of one tier that have a key on this machine (SR-02)."""
    settings = config or load_config()
    out = []
    for row in settings.providers:
        if row.tier != tier:
            continue
        if row.key is not None and not keys.available(row.key):
            continue
        out.append(row.name)
    return out
