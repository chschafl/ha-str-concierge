"""Tests for the Host Tools provider (HTTP mocked with aioresponses)."""
from __future__ import annotations

import pytest
from aioresponses import aioresponses

from custom_components.str_concierge.providers.host_tools import BASE_URL, HostToolsProvider


LISTING_RESPONSE = [
    {"_id": "listing-1", "nickname": "Beach House"},
    {"_id": "listing-2", "nickname": "Mountain Cabin"},
]

RESERVATIONS_RESPONSE = [
    {
        "_id": "res-001",
        "guestName": "Alice Smith",
        "guestEmail": "alice@example.com",
        "guestPhone": "+1-555-0100",
        "startDate": "2025-06-01T15:00:00Z",
        "endDate": "2099-12-31T11:00:00Z",
        "doorCode": "1234",
        "status": "confirmed",
    },
    {
        "_id": "res-002",
        "guestName": "Bob Jones",
        "guestEmail": "bob@example.com",
        "guestPhone": "+1-555-0200",
        "startDate": "2100-01-02T15:00:00Z",
        "endDate": "2100-01-05T11:00:00Z",
        "doorCode": "5678",
        "status": "confirmed",
    },
]


@pytest.fixture
def provider():
    return HostToolsProvider(api_key="test-token")


class TestGetProperties:
    async def test_returns_property_list(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/listings", payload=LISTING_RESPONSE)
            props = await provider.get_properties()

        assert len(props) == 2
        assert props[0].id == "listing-1"
        assert props[0].name == "Beach House"

    async def test_handles_wrapped_response(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/listings", payload={"listings": LISTING_RESPONSE})
            props = await provider.get_properties()
        assert len(props) == 2

    async def test_raises_on_http_error(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/listings", status=401)
            with pytest.raises(Exception):
                await provider.get_properties()


class TestGetPropertyData:
    async def test_current_and_next_resolved(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/reservations", payload=RESERVATIONS_RESPONSE)
            data = await provider.get_property_data("listing-1")

        assert data.current_guest is not None
        assert data.current_guest.booking_id == "res-001"
        assert data.current_guest.name == "Alice Smith"
        assert data.current_guest.door_code == "1234"

        assert data.next_guest is not None
        assert data.next_guest.booking_id == "res-002"

    async def test_no_reservations_returns_none_guests(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/reservations", payload=[])
            data = await provider.get_property_data("listing-1")
        assert data.current_guest is None
        assert data.next_guest is None


class TestMarkActions:
    async def test_mark_arrived(self, provider):
        with aioresponses() as m:
            m.patch(f"{BASE_URL}/reservations/res-001", payload={"status": "arrived"})
            result = await provider.mark_arrived("res-001")
        assert result is True

    async def test_mark_checked_out(self, provider):
        with aioresponses() as m:
            m.patch(f"{BASE_URL}/reservations/res-001", payload={"status": "checked_out"})
            result = await provider.mark_checked_out("res-001")
        assert result is True


class TestFieldMapping:
    async def test_alternate_field_names(self, provider):
        alt_response = [
            {
                "id": "res-alt",
                "guest_name": "Carol",
                "checkIn": "2025-06-01T15:00:00Z",
                "checkOut": "2099-12-31T11:00:00Z",
                "access_code": "9999",
            }
        ]
        with aioresponses() as m:
            m.get(f"{BASE_URL}/reservations", payload=alt_response)
            data = await provider.get_property_data("listing-1")

        assert data.current_guest is not None
        assert data.current_guest.booking_id == "res-alt"
        assert data.current_guest.name == "Carol"
        assert data.current_guest.door_code == "9999"
