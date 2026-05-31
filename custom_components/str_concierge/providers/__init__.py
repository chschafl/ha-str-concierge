"""Provider factory."""

from __future__ import annotations

from ..const import (
    PROVIDER_CUSTOM,
    PROVIDER_GUESTY,
    PROVIDER_HOST_TOOLS,
    PROVIDER_HOSTFULLY,
)
from .base import STRProvider
from .custom_endpoint import CustomEndpointProvider
from .guesty import GuestyProvider
from .host_tools import HostToolsProvider
from .hostfully import HostfullyProvider


def create_provider(
    provider_type: str,
    api_key: str,
    base_url: str | None = None,
    **extra,
) -> STRProvider:
    """Instantiate the correct provider for the given type.

    ``extra`` carries provider-specific config that doesn't fit the common
    (api_key, base_url) shape — e.g. ``host_tools_listing_id`` for Host Tools,
    which has no listings-list endpoint and so needs the listing ID up front.
    """
    if provider_type == PROVIDER_HOST_TOOLS:
        return HostToolsProvider(
            api_key, base_url, listing_id=extra.get("host_tools_listing_id")
        )
    if provider_type == PROVIDER_CUSTOM:
        if not base_url:
            raise ValueError("Custom endpoint provider requires a base_url")
        return CustomEndpointProvider(api_key, base_url)
    if provider_type == PROVIDER_HOSTFULLY:
        return HostfullyProvider(api_key, base_url)
    if provider_type == PROVIDER_GUESTY:
        return GuestyProvider(api_key, base_url)
    raise ValueError(f"Unknown provider type: {provider_type}")
