"""Host Tools provider.

API base: ``https://app.hosttools.com/api`` (no ``/v1`` path segment)
Authentication: custom header ``authToken: <token>`` — **not** ``Authorization: Bearer``.

The Host Tools public API does NOT expose a "list my listings" endpoint, so
the listing ID is collected during the integration's setup flow and stored
in the config entry. ``get_properties()`` returns a single synthetic
:class:`Property` so the rest of the integration can be agnostic.

Key endpoints used:
  GET /getReservations/{listingId}/{startDate}/{endDate}
      → list of reservations whose [checkIn, checkOut] overlaps the window

Reservation fields we care about (with fallback aliases — Host Tools is
inconsistent across endpoints and integration sources):

    _id / id / confirmationCode          → booking_id
    guestFirstName + guestLastName       → name (also: firstName + lastName)
    checkIn / startDate                  → checkin
    checkOut / endDate                   → checkout
    doorCode / door_code                 → door_code
    status / reservationStatus           → filter; we keep only "accepted",
                                           "confirmed", "pending", "inquiry"
                                           and skip "cancelled", "canceled",
                                           "declined", "blocked"

The Host Tools API also has a ``POST /setreservation/{id}`` endpoint for
updating door codes / guidebook URLs, but does not have an "advance the
reservation status to arrived/checked-out" concept that maps to our
``mark_arrived`` / ``mark_checked_out``. We therefore inherit the base
class's ``NotImplementedError`` for those — the integration's local state
remains the source of truth for guest lifecycle.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiohttp

from .base import Guest, Property, PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://app.hosttools.com/api"

# Reservation look-ahead. Captures a still-active checkout from earlier today
# plus everything booked for the next ~6 months — enough for `current` and
# `next` derivation without pulling the whole calendar.
LOOKBACK = timedelta(days=1)
LOOKAHEAD = timedelta(days=180)

ACTIVE_STATUSES = {"accepted", "confirmed", "pending", "inquiry"}
SKIP_STATUSES = {"cancelled", "canceled", "declined", "blocked"}


def _first(data: dict, keys: list[str], default=None):
    """Return the first non-empty value found under any of ``keys``."""
    for k in keys:
        v = data.get(k)
        if v not in (None, ""):
            return v
    return default


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    _LOGGER.warning("Could not parse datetime: %s", value)
    return None


def _ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


class HostToolsProvider(STRProvider):
    """Provider backed by the Host Tools public API."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        listing_id: str | None = None,
    ) -> None:
        super().__init__(api_key, base_url or BASE_URL)
        self._listing_id = listing_id

    # ── HTTP ──────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        # NB: Host Tools uses a custom `authToken` header, NOT `Authorization`.
        return {
            "Accept": "application/json",
            "authToken": self._api_key,
        }

    async def _get(self, path: str) -> list | dict:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ── STRProvider interface ─────────────────────────────────────────

    async def get_properties(self) -> list[Property]:
        """Return the (single) configured listing.

        Host Tools doesn't expose a listings list endpoint, so the user
        supplied the listing ID during setup. We use a one-day reservation
        fetch as the credential-validation probe — any HTTP error here
        bubbles up and the config flow shows ``cannot_connect``.
        """
        if not self._listing_id:
            raise ValueError(
                "Host Tools requires a listing ID. Re-add the integration "
                "and enter your listing ID during setup."
            )
        today = datetime.now(timezone.utc)
        # Probe call validates auth header + listing existence in one shot.
        await self._get(
            f"/getReservations/{self._listing_id}/{_ymd(today)}/{_ymd(today + timedelta(days=1))}"
        )
        return [Property(id=self._listing_id, name=self._listing_id)]

    async def get_property_data(self, property_id: str) -> PropertyData:
        now = datetime.now(timezone.utc)
        data = await self._get(
            f"/getReservations/{property_id}/{_ymd(now - LOOKBACK)}/{_ymd(now + LOOKAHEAD)}"
        )

        items = (
            data
            if isinstance(data, list)
            else data.get("reservations", data.get("data", []))
        )

        guests = [g for raw in items if (g := self._parse_reservation(raw)) is not None]
        current, next_guest = (
            self._pick_current_and_next(guests) if guests else (None, None)
        )

        return PropertyData(
            property_id=property_id,
            property_name=property_id,
            current_guest=current,
            next_guest=next_guest,
        )

    # ── Parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_reservation(raw: dict) -> Guest | None:
        status = str(
            _first(raw, ["status", "reservationStatus"], "accepted")
        ).lower().strip()
        if status in SKIP_STATUSES or status not in ACTIVE_STATUSES:
            return None

        booking_id = _first(
            raw, ["_id", "id", "confirmationCode", "confirmation_code"]
        )
        checkin = _parse_dt(_first(raw, ["checkIn", "startDate", "start_date"]))
        checkout = _parse_dt(_first(raw, ["checkOut", "endDate", "end_date"]))

        if not all([booking_id, checkin, checkout]):
            _LOGGER.debug("Skipping incomplete reservation: %s", raw)
            return None

        first = _first(raw, ["guestFirstName", "firstName"], "")
        last = _first(raw, ["guestLastName", "lastName"], "")
        name = (
            f"{first} {last}".strip()
            or _first(raw, ["guestName", "name"], "Unknown")
        )

        return Guest(
            booking_id=str(booking_id),
            name=name,
            checkin=checkin,
            checkout=checkout,
            door_code=_first(raw, ["doorCode", "door_code"]),
        )
