"""Hostfully provider.

API reference: https://dev.hostfully.com/reference/getting-started

Authentication: API key passed as X-HOSTFULLY-APIKEY header.
Base URL: https://api.hostfully.com/v3

Bookings are "Leads" in Hostfully's model. A confirmed booking has
status BOOKED or PAID_IN_FULL.

Key endpoints:
  GET /agencies              → list agencies (pick first unless configured)
  GET /properties            → list properties
  GET /leads?agencyUid=&propertyUid=&fromDate=&toDate=
                             → paginated list of leads/bookings
  PUT /leads/{uid}/checkIn   → mark arrived
  PUT /leads/{uid}/checkOut  → mark checked out
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import aiohttp

from .base import Guest, Property, PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.hostfully.com/v3"
ACTIVE_STATUSES = {"BOOKED", "PAID_IN_FULL", "CHECKED_IN"}


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
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None


class HostfullyProvider(STRProvider):
    """Provider backed by the Hostfully PMP API v3."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        lookahead_days: int = 30,
    ) -> None:
        super().__init__(api_key, base_url or BASE_URL)
        self._agency_uid: str | None = None
        self._lookahead = timedelta(days=lookahead_days)

    def _headers(self) -> dict:
        return {
            "X-HOSTFULLY-APIKEY": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._headers(), params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _put(self, path: str) -> dict:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _ensure_agency(self) -> str:
        if self._agency_uid:
            return self._agency_uid
        data = await self._get("/agencies")
        agencies = data if isinstance(data, list) else data.get("agencies", [])
        if not agencies:
            raise RuntimeError("No Hostfully agencies found for this API key")
        self._agency_uid = agencies[0].get("uid") or agencies[0].get("agencyUid")
        return self._agency_uid

    @staticmethod
    def _parse_lead(raw: dict) -> Guest | None:
        checkin_str = raw.get("checkInDate") or raw.get("startDate")
        checkout_str = raw.get("checkOutDate") or raw.get("endDate")
        uid = raw.get("uid") or raw.get("id")

        checkin = _parse_dt(checkin_str)
        checkout = _parse_dt(checkout_str)
        if not all([uid, checkin, checkout]):
            return None

        first = raw.get("guestFirstName", "")
        last = raw.get("guestLastName", "")
        name = f"{first} {last}".strip() or raw.get("guestName", "Unknown")

        return Guest(
            booking_id=str(uid),
            name=name,
            checkin=checkin,
            checkout=checkout,
            door_code=raw.get("accessCode"),
        )

    async def get_properties(self) -> list[Property]:
        agency_uid = await self._ensure_agency()
        data = await self._get("/properties", params={"agencyUid": agency_uid})
        items = data if isinstance(data, list) else data.get("properties", [])
        return [
            Property(
                id=str(p.get("uid") or p.get("id")),
                name=p.get("name") or p.get("nickname") or str(p.get("uid")),
            )
            for p in items
            if p.get("uid") or p.get("id")
        ]

    async def get_property_data(self, property_id: str) -> PropertyData:
        agency_uid = await self._ensure_agency()
        now = datetime.now(UTC)
        from_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = (now + self._lookahead).strftime("%Y-%m-%d")

        data = await self._get(
            "/leads",
            params={
                "agencyUid": agency_uid,
                "propertyUid": property_id,
                "fromDate": from_date,
                "toDate": to_date,
                "status": ",".join(ACTIVE_STATUSES),
            },
        )
        items = data if isinstance(data, list) else data.get("leads", data.get("data", []))
        guests = [g for raw in items if (g := self._parse_lead(raw))]
        current, next_guest = self._pick_current_and_next(guests) if guests else (None, None)
        return PropertyData(
            property_id=property_id,
            property_name=property_id,
            current_guest=current,
            next_guest=next_guest,
        )

    async def mark_arrived(self, booking_id: str) -> bool:
        await self._put(f"/leads/{booking_id}/checkIn")
        return True

    async def mark_checked_out(self, booking_id: str) -> bool:
        await self._put(f"/leads/{booking_id}/checkOut")
        return True
