"""Host Tools provider.

API reference: https://help.hosttools.com/en/articles/10118922-host-tools-api-docs

Authentication: Bearer token passed as Authorization header.
Base URL: https://app.hosttools.com/api/v1

Key endpoints used:
  GET /listings              – list properties
  GET /reservations          – all upcoming/active reservations (optional ?listingId=)
  PATCH /reservations/{id}   – update reservation status (arrived / checked_out)

Field mapping from Host Tools JSON → our Guest model:
  _id            → booking_id
  guestName      → name
  guestEmail     → email
  guestPhone     → phone
  startDate      → checkin  (ISO-8601)
  endDate        → checkout (ISO-8601)
  doorCode       → door_code
  status         → status

If Host Tools changes their field names, adjust the _FIELD_MAP constant below.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp

from .base import Guest, Property, PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://app.hosttools.com/api/v1"

# Map Host Tools JSON keys → our dataclass field names.
# Adjust here if the actual API uses different names.
_RESERVATION_FIELD_MAP = {
    "booking_id": ["_id", "id", "reservationId"],
    "name": ["guestName", "guest_name", "name"],
    "email": ["guestEmail", "guest_email", "email"],
    "phone": ["guestPhone", "guest_phone", "phone"],
    "checkin": ["startDate", "checkIn", "check_in", "start_date"],
    "checkout": ["endDate", "checkOut", "check_out", "end_date"],
    "door_code": ["doorCode", "door_code", "accessCode", "access_code"],
    "status": ["status"],
}

_LISTING_FIELD_MAP = {
    "id": ["_id", "id", "listingId"],
    "name": ["nickname", "name", "title"],
}


def _first(data: dict, keys: list[str], default=None):
    for k in keys:
        if k in data:
            return data[k]
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


class HostToolsProvider(STRProvider):
    """Provider backed by the Host Tools public API."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(api_key, base_url or BASE_URL)

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> list | dict:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._headers(), params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _patch(self, path: str, data: dict) -> dict:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                url, headers=self._headers(), json=data, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    # Data parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_reservation(raw: dict) -> Guest | None:
        checkin = _parse_dt(_first(raw, _RESERVATION_FIELD_MAP["checkin"]))
        checkout = _parse_dt(_first(raw, _RESERVATION_FIELD_MAP["checkout"]))
        booking_id = _first(raw, _RESERVATION_FIELD_MAP["booking_id"])

        if not all([checkin, checkout, booking_id]):
            _LOGGER.debug("Skipping incomplete reservation: %s", raw)
            return None

        return Guest(
            booking_id=str(booking_id),
            name=_first(raw, _RESERVATION_FIELD_MAP["name"], "Unknown"),
            email=_first(raw, _RESERVATION_FIELD_MAP["email"]),
            phone=_first(raw, _RESERVATION_FIELD_MAP["phone"]),
            checkin=checkin,
            checkout=checkout,
            door_code=_first(raw, _RESERVATION_FIELD_MAP["door_code"]),
            status=_first(raw, _RESERVATION_FIELD_MAP["status"], "confirmed"),
        )

    @staticmethod
    def _parse_listing(raw: dict) -> Property | None:
        listing_id = _first(raw, _LISTING_FIELD_MAP["id"])
        name = _first(raw, _LISTING_FIELD_MAP["name"], str(listing_id))
        if not listing_id:
            return None
        return Property(id=str(listing_id), name=name)

    # ------------------------------------------------------------------
    # STRProvider interface
    # ------------------------------------------------------------------

    async def get_properties(self) -> list[Property]:
        data = await self._get("/listings")
        items = data if isinstance(data, list) else data.get("listings", data.get("data", []))
        return [p for raw in items if (p := self._parse_listing(raw))]

    async def get_property_data(self, property_id: str) -> PropertyData:
        data = await self._get("/reservations", params={"listingId": property_id})
        items = data if isinstance(data, list) else data.get("reservations", data.get("data", []))

        guests = [g for raw in items if (g := self._parse_reservation(raw))]
        current, next_guest = self._pick_current_and_next(guests) if guests else (None, None)

        return PropertyData(
            property_id=property_id,
            property_name=property_id,
            current_guest=current,
            next_guest=next_guest,
        )

    async def mark_arrived(self, booking_id: str) -> bool:
        await self._patch(f"/reservations/{booking_id}", {"status": "arrived"})
        return True

    async def mark_checked_out(self, booking_id: str) -> bool:
        await self._patch(f"/reservations/{booking_id}", {"status": "checked_out"})
        return True
