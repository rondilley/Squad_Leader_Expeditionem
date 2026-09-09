"""The provider adapters. One interface, one thin adapter for each provider (IR-02)."""

from slagents.prompted.providers.base import (
    Provider,
    ProviderConfig,
    ProviderError,
    ProviderUnavailable,
    Answer,
    allowed_host,
    load_config,
    make_provider,
    providers_for,
)

__all__ = [
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "ProviderUnavailable",
    "Answer",
    "allowed_host",
    "load_config",
    "make_provider",
    "providers_for",
]
