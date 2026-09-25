"""The provider router with the failover sequence and the circuit breaker (IR-05, TC-22).

A run names a sequence of providers. The router calls the first one that its breaker
allows. When that call fails, the router records the failure, opens the breaker after a
count of failures, and moves to the next provider in the sequence.

The breaker closes again after a rest, because a provider that was busy for a minute is
not a provider that is gone. A breaker that never closes turns one timeout into a run with
one provider.

A failure counts toward the breaker only when a rest can cure it: a timeout, a network
error, 408, 429, or a 5xx (`is_transient`). A 400 comes back on each call with the same
request, so before this correction (L6) one prompt that a provider refused opened the
breaker of each host of a pool in turn, and the run went on with no provider. Such a
failure still moves the call to the next provider, and the failover record says it was
not counted.

The router gives the same `complete` as one provider, so the harness does not know whether
it talks to one provider or to five.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from slagents.prompted.providers import Answer, Provider, ProviderError, ProviderUnavailable
from slagents.prompted.providers.base import is_transient

FAILURES_TO_OPEN = 2
REST_SECONDS = 60.0


@dataclass
class Breaker:
    """The state of one provider in the router."""

    name: str
    failures: int = 0
    opened_at: float = 0.0
    calls: int = 0
    successes: int = 0

    def open(self, now: float, threshold: int, rest: float) -> bool:
        """True when this provider is out of the sequence at this moment."""
        if self.failures < threshold:
            return False
        return now - self.opened_at < rest

    def record_failure(self, now: float) -> None:
        self.failures += 1
        self.opened_at = now

    def record_success(self) -> None:
        self.failures = 0
        self.successes += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
        }


class Router:
    """A sequence of providers with one interface (IR-05)."""

    def __init__(
        self,
        providers: Sequence[Provider],
        failures_to_open: int = FAILURES_TO_OPEN,
        rest_seconds: float = REST_SECONDS,
    ) -> None:
        if not providers:
            raise ProviderError("the router needs one provider or more")
        self.providers = list(providers)
        self.failures_to_open = failures_to_open
        self.rest_seconds = rest_seconds
        self.breakers = {p.name: Breaker(p.name) for p in self.providers}
        self.failovers: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "+".join(p.name for p in self.providers)

    @property
    def model(self) -> str:
        return self.providers[0].model

    def health(self) -> bool:
        return any(p.health() for p in self.providers)

    def supports_constraint(self) -> bool:
        return all(p.supports_constraint() for p in self.providers)

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 700,
        temperature: float = 0.2,
        json_schema: Any = None,
    ) -> Answer:
        """The answer of the first provider that gives one."""
        now = time.monotonic()
        last: ProviderError | None = None
        tried: list[str] = []
        for provider in self.providers:
            breaker = self.breakers[provider.name]
            if breaker.open(now, self.failures_to_open, self.rest_seconds):
                self.failovers.append({"provider": provider.name, "cause": "the breaker is open"})
                continue
            tried.append(provider.name)
            breaker.calls += 1
            try:
                answer = provider.complete(system, user, max_tokens, temperature, json_schema)
            except ProviderError as exc:
                transient = is_transient(exc)
                if transient:
                    breaker.record_failure(time.monotonic())
                last = exc
                self.failovers.append(
                    {
                        "provider": provider.name,
                        "cause": str(exc)[:200],
                        "status": exc.status,
                        "counted": transient,
                        "failures": breaker.failures,
                        "breaker_open": breaker.failures >= self.failures_to_open,
                    }
                )
                continue
            breaker.record_success()
            return answer
        raise ProviderUnavailable(
            f"no provider answered. The router tried {tried or 'none, because each breaker is open'}. "
            f"The last cause: {last}"
        )

    def report(self) -> dict[str, Any]:
        """What the run artifact records about the router (IR-04, TC-22)."""
        return {
            "sequence": [p.name for p in self.providers],
            "breakers": [b.to_dict() for b in self.breakers.values()],
            "failovers": self.failovers,
        }
