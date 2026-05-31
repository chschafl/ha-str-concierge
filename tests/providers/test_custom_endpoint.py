"""Tests for the Custom Endpoint provider."""
from __future__ import annotations

import pytest
from aioresponses import aioresponses

from custom_components.str_concierge.providers.custom_endpoint import CustomEndpointProvider

BASE = "https://my-api.example.com/api"

PROPS_RESPONSE = [{"id": "p1", "name": "My Villa"}]

RESERVATIONS_RESPONSE = [
    {
        "id": "r1",
        "guestName": "Dana",
        "checkIn": "2025-06-01T14:00:00Z",
        "checkOut": "2099-12-31T10:00:00Z",
        "doorCode": "4321",
        "status": "confirmed",
    }
]


@pytest.fixture
def provider():
    return CustomEndpointProvider(api_key="my-token", base_url=BASE)


class TestCustomEndpoint:
    async def test_get_properties(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE}/properties", payload=PROPS_RESPONSE)
            props = await provider.get_properties()
        assert props[0].id == "p1"
        assert props[0].name == "My Villa"

    async def test_get_property_data(self, provider):
        with aioresponses() as m:
            m.get(
                f"{BASE}/properties/p1/reservations",
                payload=RESERVATIONS_RESPONSE,
            )
            data = await provider.get_property_data("p1")
        assert data.current_guest.name == "Dana"
        assert data.current_guest.door_code == "4321"

    async def test_mark_arrive(self, provider):
        with aioresponses() as m:
            # mark_arrived needs the property_id, which is stashed by the
            # first get_property_data call.
            m.get(f"{BASE}/properties/p1/reservations", payload=[])
            m.post(
                f"{BASE}/properties/p1/reservations/r1/arrive",
                payload={"ok": True},
            )
            await provider.get_property_data("p1")
            result = await provider.mark_arrived("r1")
        assert result is True

    async def test_mark_checkout(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE}/properties/p1/reservations", payload=[])
            m.post(
                f"{BASE}/properties/p1/reservations/r1/checkout",
                payload={"ok": True},
            )
            await provider.get_property_data("p1")
            result = await provider.mark_checked_out("r1")
        assert result is True

    async def test_mark_actions_fail_before_property_known(self, provider):
        """Defensive: don't blindly POST without a property_id."""
        with pytest.raises(RuntimeError, match="property_id"):
            await provider.mark_arrived("r1")
        with pytest.raises(RuntimeError, match="property_id"):
            await provider.mark_checked_out("r1")

    async def test_trailing_slash_stripped(self):
        p = CustomEndpointProvider(api_key="t", base_url=f"{BASE}/")
        with aioresponses() as m:
            m.get(f"{BASE}/properties", payload=[])
            await p.get_properties()
