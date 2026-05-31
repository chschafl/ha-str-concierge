"""Tests for the Host Tools provider (HTTP mocked with aioresponses)."""
from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from custom_components.str_concierge.providers.host_tools import (
    BASE_URL,
    HostToolsProvider,
)


# The reservations endpoint embeds dates in the path, so tests match by regex.
RESERVATIONS_URL_RE = re.compile(
    rf"{re.escape(BASE_URL)}/getReservations/listing-1/\d{{4}}-\d{{2}}-\d{{2}}/\d{{4}}-\d{{2}}-\d{{2}}"
)

RESERVATIONS_RESPONSE = [
    {
        "_id": "res-001",
        "guestFirstName": "Alice",
        "guestLastName": "Smith",
        "checkIn": "2025-06-01T15:00:00Z",
        "checkOut": "2099-12-31T11:00:00Z",
        "doorCode": "1234",
        "status": "accepted",
    },
    {
        "_id": "res-002",
        "guestFirstName": "Bob",
        "guestLastName": "Jones",
        "checkIn": "2100-01-02T15:00:00Z",
        "checkOut": "2100-01-05T11:00:00Z",
        "doorCode": "5678",
        "status": "confirmed",
    },
    {
        "_id": "res-cancelled",
        "guestFirstName": "Carol",
        "guestLastName": "Cancel",
        "checkIn": "2100-02-01T15:00:00Z",
        "checkOut": "2100-02-05T11:00:00Z",
        "status": "cancelled",
    },
    {
        "_id": "res-block",
        "checkIn": "2100-03-01T15:00:00Z",
        "checkOut": "2100-03-05T11:00:00Z",
        "status": "blocked",
    },
]


@pytest.fixture
def provider():
    return HostToolsProvider(api_key="test-token", listing_id="listing-1")


class TestGetProperties:
    async def test_returns_configured_listing(self, provider):
        """get_properties uses a 1-day reservations call as the auth probe."""
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=[])
            props = await provider.get_properties()
        assert len(props) == 1
        assert props[0].id == "listing-1"

    async def test_raises_on_http_error(self, provider):
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, status=401)
            with pytest.raises(Exception):
                await provider.get_properties()

    async def test_raises_without_listing_id(self):
        bad = HostToolsProvider(api_key="t", listing_id=None)
        with pytest.raises(ValueError, match="listing ID"):
            await bad.get_properties()


class TestGetPropertyData:
    async def test_current_and_next_resolved(self, provider):
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=RESERVATIONS_RESPONSE)
            data = await provider.get_property_data("listing-1")

        assert data.current_guest is not None
        assert data.current_guest.booking_id == "res-001"
        assert data.current_guest.name == "Alice Smith"
        assert data.current_guest.door_code == "1234"

        assert data.next_guest is not None
        assert data.next_guest.booking_id == "res-002"

    async def test_cancelled_and_blocked_are_filtered_out(self, provider):
        """Cancelled / blocked entries must not show up as `current` or `next`."""
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=RESERVATIONS_RESPONSE)
            data = await provider.get_property_data("listing-1")
        # res-cancelled and res-block must not bleed in.
        assert data.next_guest.booking_id == "res-002"

    async def test_no_reservations_returns_none_guests(self, provider):
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=[])
            data = await provider.get_property_data("listing-1")
        assert data.current_guest is None
        assert data.next_guest is None

    async def test_handles_wrapped_envelope(self, provider):
        with aioresponses() as m:
            m.get(
                RESERVATIONS_URL_RE,
                payload={"reservations": RESERVATIONS_RESPONSE},
            )
            data = await provider.get_property_data("listing-1")
        assert data.current_guest is not None
        assert data.current_guest.booking_id == "res-001"


class TestFieldMapping:
    async def test_alternate_field_names(self, provider):
        alt_response = [
            {
                "id": "res-alt",                   # `id` instead of `_id`
                "firstName": "Carol",              # firstName/lastName instead of guestFirstName/Last
                "lastName": "Lee",
                "startDate": "2025-06-01T15:00:00Z",  # startDate instead of checkIn
                "endDate": "2099-12-31T11:00:00Z",
                "door_code": "9999",               # snake_case
                "reservationStatus": "accepted",   # reservationStatus instead of status
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=alt_response)
            data = await provider.get_property_data("listing-1")

        assert data.current_guest is not None
        assert data.current_guest.booking_id == "res-alt"
        assert data.current_guest.name == "Carol Lee"
        assert data.current_guest.door_code == "9999"

    async def test_falls_back_to_guestName(self, provider):
        """When first/last aren't present, accept a flat guestName field."""
        alt_response = [
            {
                "_id": "res-x",
                "guestName": "Single Name",
                "checkIn": "2025-06-01T15:00:00Z",
                "checkOut": "2099-12-31T11:00:00Z",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=alt_response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.name == "Single Name"


class TestAuthHeader:
    async def test_sends_authToken_header_not_bearer(self, provider):
        """Host Tools uses `authToken: <key>`, not Authorization: Bearer."""
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=[])
            await provider.get_property_data("listing-1")
            # Inspect the recorded request.
            (call_args,) = next(iter(m.requests.values()))
            headers = call_args.kwargs.get("headers", {})
            assert headers.get("authToken") == "test-token"
            assert "Authorization" not in headers
