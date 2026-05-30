"""Custom/homebrew backend provider.

Expects a REST API at a user-supplied base URL with these endpoints:

  GET  {base_url}/properties
       → [{"id": "...", "name": "..."}]

  GET  {base_url}/reservations?propertyId={id}
       → [{"id": "...", "guestName": "...", "guestEmail": "...",
            "guestPhone": "...", "checkIn": "ISO-8601",
            "checkOut": "ISO-8601", "doorCode": "...", "status": "..."}]

  POST {base_url}/reservations/{id}/arrive   → {"ok": true}
  POST {base_url}/reservations/{id}/checkout → {"ok": true}

Authentication: Bearer token via Authorization header.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp

from .base import Guest, Property, PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)

DEFAULT_FIELD_MAP = {
    "prop_id": ["id"],
    "prop_name": ["name"],
    "booking_id": ["id"],
    "name": ["guestName", "guest_name", "name"],
    "email": ["guestEmail", "guest_email", "email"],
    "phone": ["guestPhone", "guest_phone", "phone"],
    "checkin": ["checkIn", "check_in", "startDate", "start_date"],
    "checkout": ["checkOut", "check_out", "endDate", "end_date"],
    "door_code": ["doorCode", "door_code", "accessCode", "pin"],
    "status": ["status"],
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


class CustomEndpointProvider(STRProvider):
    """Provider for a user-operated custom backend."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        field_map: dict | None = None,
    ) -> None:
        super().__init__(api_key, base_url.rstrip("/"))
        self._field_map = {**DEFAULT_FIELD_MAP, **(field_map or {})}

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

    async def _post(self, path: str) -> dict:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    def _parse_reservation(self, raw: dict) -> Guest | None:
        fm = self._field_map
        checkin = _parse_dt(_first(raw, fm["checkin"]))
        checkout = _parse_dt(_first(raw, fm["checkout"]))
        booking_id = _first(raw, fm["booking_id"])
        if not all([checkin, checkout, booking_id]):
            return None
        return Guest(
            booking_id=str(booking_id),
            name=_first(raw, fm["name"], "Unknown"),
            email=_first(raw, fm["email"]),
            phone=_first(raw, fm["phone"]),
            checkin=checkin,
            checkout=checkout,
            door_code=_first(raw, fm["door_code"]),
            status=_first(raw, fm["status"], "confirmed"),
        )

    def _parse_property(self, raw: dict) -> Property | None:
        fm = self._field_map
        prop_id = _first(raw, fm["prop_id"])
        name = _first(raw, fm["prop_name"], str(prop_id))
        if not prop_id:
            return None
        return Property(id=str(prop_id), name=name)

    async def get_properties(self) -> list[Property]:
        data = await self._get("/properties")
        items = data if isinstance(data, list) else data.get("properties", data.get("data", []))
        return [p for raw in items if (p := self._parse_property(raw))]

    async def get_property_data(self, property_id: str) -> PropertyData:
        data = await self._get("/reservations", params={"propertyId": property_id})
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
        await self._post(f"/reservations/{booking_id}/arrive")
        return True

    async def mark_checked_out(self, booking_id: str) -> bool:
        await self._post(f"/reservations/{booking_id}/checkout")
        return True
