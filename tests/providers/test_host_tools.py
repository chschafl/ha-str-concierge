"""Tests for the Host Tools provider (HTTP mocked with aioresponses)."""
from __future__ import annotations

import re
from datetime import UTC
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aioresponses import aioresponses
from homeassistant.util import dt as dt_util

from custom_components.str_concierge.providers.host_tools import (
    BASE_URL,
    HostToolsProvider,
)

# The reservations endpoint embeds dates in the path, so tests match by regex.
RESERVATIONS_URL_RE = re.compile(
    rf"{re.escape(BASE_URL)}/getReservations/listing-1/\d{{4}}-\d{{2}}-\d{{2}}/\d{{4}}-\d{{2}}-\d{{2}}"
)

LISTINGS_RESPONSE = [
    {"_id": "listing-1", "nickname": "Beach House"},
    {"_id": "listing-2", "nickname": "Mountain Cabin"},
]

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
    return HostToolsProvider(api_key="test-token")


class TestGetProperties:
    async def test_returns_listings_from_api(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/getListings", payload=LISTINGS_RESPONSE)
            props = await provider.get_properties()
        assert [p.id for p in props] == ["listing-1", "listing-2"]
        assert props[0].name == "Beach House"

    async def test_handles_wrapped_envelope(self, provider):
        with aioresponses() as m:
            m.get(
                f"{BASE_URL}/getListings",
                payload={"listings": LISTINGS_RESPONSE},
            )
            props = await provider.get_properties()
        assert len(props) == 2

    async def test_alternate_listing_field_names(self, provider):
        alt = [{"id": "alt-1", "title": "Lakeside Loft"}]
        with aioresponses() as m:
            m.get(f"{BASE_URL}/getListings", payload=alt)
            props = await provider.get_properties()
        assert props[0].id == "alt-1"
        assert props[0].name == "Lakeside Loft"

    async def test_raises_on_http_error(self, provider):
        with aioresponses() as m:
            m.get(f"{BASE_URL}/getListings", status=401)
            with pytest.raises(aiohttp.ClientResponseError):
                await provider.get_properties()


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


class TestFieldMapping:
    async def test_alternate_reservation_field_names(self, provider):
        alt_response = [
            {
                "id": "res-alt",                       # `id` instead of `_id`
                # firstName/lastName instead of guestFirstName/Last
                "firstName": "Carol",
                "lastName": "Lee",
                # startDate instead of checkIn
                "startDate": "2025-06-01T15:00:00Z",
                "endDate": "2099-12-31T11:00:00Z",
                "door_code": "9999",                   # snake_case
                "reservationStatus": "accepted",       # reservationStatus instead of status
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
            m.get(f"{BASE_URL}/getListings", payload=[])
            await provider.get_properties()
            (call_args,) = next(iter(m.requests.values()))
            headers = call_args.kwargs.get("headers", {})
            assert headers.get("authToken") == "test-token"
            assert "Authorization" not in headers


@pytest.fixture
def utc_tz():
    """Ensure HA's default timezone is UTC for tests that don't care about TZ."""
    prev = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(dt_util.UTC)
    yield
    dt_util.set_default_time_zone(prev)


@pytest.fixture
def vienna_tz():
    """Run a test under Europe/Vienna (UTC+1 winter / UTC+2 summer DST)."""
    prev = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Europe/Vienna"))
    yield
    dt_util.set_default_time_zone(prev)


@pytest.fixture
def la_tz():
    """Run a test under America/Los_Angeles (PST/PDT — UTC-7 / UTC-8)."""
    prev = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("America/Los_Angeles"))
    yield
    dt_util.set_default_time_zone(prev)


class TestCheckInOutTimes:
    """Host Tools sends date and time-of-day as separate fields. Verify the
    combiner treats the time as HA-local and converts to UTC."""

    async def test_combines_date_with_numeric_hour(self, provider, utc_tz):
        response = [
            {
                "_id": "res-numeric",
                "guestName": "Numeric Hour",
                "checkIn": "2025-06-01",      # date only
                "checkInTime": 16,             # 4pm as numeric
                "checkOut": "2099-12-31",
                "checkOutTime": 11,
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        # HA tz is UTC, so 16:00 local == 16:00 UTC.
        assert data.current_guest.checkin.hour == 16
        assert data.current_guest.checkin.minute == 0
        assert data.current_guest.checkout.hour == 11

    async def test_combines_date_with_string_hhmm(self, provider, utc_tz):
        response = [
            {
                "_id": "res-hhmm",
                "guestName": "HHMM String",
                "checkIn": "2025-06-01",
                "checkInTime": "15:30",
                "checkOut": "2099-12-31",
                "checkOutTime": "11:00",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.checkin.hour == 15
        assert data.current_guest.checkin.minute == 30

    async def test_combines_date_with_12_hour_string(self, provider, utc_tz):
        response = [
            {
                "_id": "res-12h",
                "guestName": "12 Hour",
                "checkIn": "2025-06-01",
                "checkInTime": "4:00 PM",
                "checkOut": "2099-12-31",
                "checkOutTime": "11 AM",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.checkin.hour == 16
        assert data.current_guest.checkout.hour == 11

    async def test_combines_fractional_numeric_hour(self, provider, utc_tz):
        response = [
            {
                "_id": "res-frac",
                "guestName": "Half Past",
                "checkIn": "2025-06-01",
                "checkInTime": 15.5,           # 3:30 pm
                "checkOut": "2099-12-31",
                "checkOutTime": 10.25,         # 10:15
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert (data.current_guest.checkin.hour, data.current_guest.checkin.minute) == (15, 30)
        assert (data.current_guest.checkout.hour, data.current_guest.checkout.minute) == (10, 15)

    async def test_falls_back_to_date_time_when_no_explicit_time(self, provider, utc_tz):
        """If only a full ISO datetime is sent (no separate time field),
        use the time embedded in the date string."""
        response = [
            {
                "_id": "res-iso",
                "guestName": "ISO Only",
                "checkIn": "2025-06-01T14:00:00Z",
                "checkOut": "2099-12-31T10:00:00Z",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.checkin.hour == 14

    async def test_date_only_without_time_defaults_to_midnight(self, provider, utc_tz):
        """Date-only without an explicit time field falls through to local
        midnight (= UTC midnight under the utc_tz fixture)."""
        response = [
            {
                "_id": "res-midnight",
                "guestName": "Midnight",
                "checkIn": "2025-06-01",
                "checkOut": "2099-12-31",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.checkin.hour == 0


class TestCheckInTimeZoneConversion:
    """When Host Tools sends a date-only field + a numeric time, the time
    refers to local wall-clock at the property (= HA's configured tz). We
    must convert that to UTC for storage so coordinator math is consistent."""

    async def test_vienna_summer_4pm_local_is_14utc(self, provider, vienna_tz):
        """June 1 is DST in Vienna (UTC+2), so 16:00 local → 14:00 UTC."""
        response = [
            {
                "_id": "res-tz-summer",
                "guestName": "Vienna Summer",
                "checkIn": "2025-06-01",
                "checkInTime": 16,
                "checkOut": "2099-12-31",
                "checkOutTime": 11,
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        # 16:00 Vienna summer = UTC+2 = 14:00 UTC
        assert data.current_guest.checkin.hour == 14
        assert data.current_guest.checkin.minute == 0
        assert data.current_guest.checkin.tzinfo == UTC

    async def test_vienna_winter_4pm_local_is_15utc(self, provider, vienna_tz):
        """January is standard time in Vienna (UTC+1), so 16:00 local → 15:00 UTC."""
        response = [
            {
                "_id": "res-tz-winter",
                "guestName": "Vienna Winter",
                "checkIn": "2025-01-15",
                "checkInTime": 16,
                "checkOut": "2099-12-31",
                "checkOutTime": 11,
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.checkin.hour == 15
        # Date may roll forward, but the time-of-day in UTC is the test point.
        assert data.current_guest.checkin.tzinfo == UTC

    async def test_iso_timestamp_with_z_is_treated_as_local(
        self, provider, vienna_tz
    ):
        """Host Tools mis-encodes property-local time as `...Z`. The integration
        ignores the embedded offset and re-interprets the time portion as local.
        So 14:00Z under Vienna summer (UTC+2) → 12:00 UTC, NOT 14:00 UTC."""
        response = [
            {
                "_id": "res-iso-host-tools-lie",
                "guestName": "ISO Mis-tagged",
                "checkIn": "2025-06-01T14:00:00Z",
                "checkOut": "2099-12-31T10:00:00Z",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        # 14:00 Vienna summer = UTC+2 → 12:00 UTC
        assert data.current_guest.checkin.hour == 12
        assert data.current_guest.checkin.tzinfo == UTC

    async def test_pst_11am_iso_z_regression(self, provider, la_tz):
        """Regression: user reported 11 AM PST check-in showing as 4 AM.
        Host Tools sent it as `T11:00:00Z`; the integration was trusting
        the `Z` instead of treating 11 as local. Now: 11 AM PDT → 18:00 UTC."""
        response = [
            {
                "_id": "res-kaite",
                "guestName": "Kaite",
                "checkIn": "2099-05-31T11:00:00Z",   # forced into the future
                "checkOut": "2099-06-02T11:00:00Z",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        # Booking is in the future → lands in next_guest. 11 AM PDT (May 31
        # is DST) = UTC-7 → 18:00 UTC.
        guest = data.next_guest or data.current_guest
        assert guest is not None
        assert guest.checkin.hour == 18
        assert guest.checkin.tzinfo == UTC

    async def test_iso_timestamp_no_explicit_time_field(self, provider):
        """When there's no separate time field, the time portion of the
        ISO string is still extracted and treated as local (HA defaults
        to UTC in tests, so 14:00 local == 14:00 UTC)."""
        response = [
            {
                "_id": "res-iso-utc-default",
                "guestName": "ISO Under UTC",
                "checkIn": "2025-06-01T14:00:00Z",
                "checkOut": "2099-12-31T10:00:00Z",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.checkin.hour == 14


class TestDoorCode:
    async def test_lock_code_field_is_canonical(self, provider):
        """Host Tools sends the door PIN under `lockCode`."""
        response = [
            {
                "_id": "res-lc",
                "guestName": "Lock Code",
                "checkIn": "2025-06-01T15:00:00Z",
                "checkOut": "2099-12-31T11:00:00Z",
                "lockCode": "9876",
                "status": "accepted",
            }
        ]
        with aioresponses() as m:
            m.get(RESERVATIONS_URL_RE, payload=response)
            data = await provider.get_property_data("listing-1")
        assert data.current_guest.door_code == "9876"

    async def test_door_code_aliases_still_work(self, provider):
        """Legacy/variant payloads can still use doorCode etc."""
        for key in ("doorCode", "door_code", "accessCode"):
            response = [
                {
                    "_id": f"res-{key}",
                    "guestName": key,
                    "checkIn": "2025-06-01T15:00:00Z",
                    "checkOut": "2099-12-31T11:00:00Z",
                    key: "1111",
                    "status": "accepted",
                }
            ]
            with aioresponses() as m:
                m.get(RESERVATIONS_URL_RE, payload=response)
                data = await provider.get_property_data("listing-1")
            assert data.current_guest.door_code == "1111", f"failed for key={key}"
