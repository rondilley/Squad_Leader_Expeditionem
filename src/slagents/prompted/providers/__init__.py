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
    pool_names,
    providers_for,
    set_pool_offset,
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
    "pool_names",
    "providers_for",
    "set_pool_offset",
]
