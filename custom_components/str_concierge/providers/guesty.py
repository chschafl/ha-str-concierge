"""Guesty provider.

API reference: https://open-api-docs.guesty.com/

Authentication: OAuth 2.0 Client Credentials flow.
  POST https://open-api.guesty.com/oauth2/token
  Body: grant_type=client_credentials&client_id=...&client_secret=...

For this integration the api_key field is interpreted as
"client_id:client_secret" (colon-separated). The token is refreshed
automatically when it expires.

Base URL: https://open-api.guesty.com/v1
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import aiohttp

from .base import Guest, Property, PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://open-api.guesty.com/v1"
TOKEN_URL = "https://open-api.guesty.com/oauth2/token"
ACTIVE_STATUSES = "confirmed,checked_in"


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


class GuestyProvider(STRProvider):
    """Provider backed by the Guesty Open API v1 (OAuth2 client credentials)."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        lookahead_days: int = 30,
    ) -> None:
        """api_key must be 'client_id:client_secret'."""
        super().__init__(api_key, base_url or BASE_URL)
        self._lookahead = timedelta(days=lookahead_days)
        parts = api_key.split(":", 1)
        if len(parts) != 2:
            raise ValueError(
                "Guesty credentials must be formatted as 'client_id:client_secret'"
            )
        self._client_id, self._client_secret = parts
        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    async def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        async with aiohttp.ClientSession() as session:
            async with session.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        self._access_token = payload["access_token"]
        self._token_expiry = time.time() + payload.get("expires_in", 86400)
        return self._access_token

    async def _headers(self) -> dict:
        token = await self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self._base_url}{path}"
        headers = await self._headers()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _put(self, path: str) -> dict:
        url = f"{self._base_url}{path}"
        headers = await self._headers()
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    @staticmethod
    def _parse_reservation(raw: dict) -> Guest | None:
        res_id = raw.get("_id") or raw.get("id")
        checkin_str = raw.get("checkIn") or raw.get("checkInDateLocalized")
        checkout_str = raw.get("checkOut") or raw.get("checkOutDateLocalized")
        checkin = _parse_dt(checkin_str)
        checkout = _parse_dt(checkout_str)
        if not all([res_id, checkin, checkout]):
            return None

        guest_data = raw.get("guest", {}) or {}
        name = (
            guest_data.get("fullName")
            or f"{guest_data.get('firstName', '')} {guest_data.get('lastName', '')}".strip()
            or "Unknown"
        )

        door_code = (
            raw.get("integration", {}).get("doorCode")
            or raw.get("doorCode")
            or raw.get("accessCode")
        )

        return Guest(
            booking_id=str(res_id),
            name=name,
            checkin=checkin,
            checkout=checkout,
            door_code=door_code,
        )

    async def get_properties(self) -> list[Property]:
        data = await self._get("/listings", params={"limit": 100})
        items = data if isinstance(data, list) else data.get("results", data.get("data", []))
        return [
            Property(
                id=str(p.get("_id") or p.get("id")),
                name=p.get("nickname") or p.get("title") or str(p.get("_id")),
            )
            for p in items
            if p.get("_id") or p.get("id")
        ]

    async def get_property_data(self, property_id: str) -> PropertyData:
        now = datetime.now(UTC)
        from_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = (now + self._lookahead).strftime("%Y-%m-%d")

        data = await self._get(
            "/reservations",
            params={
                "listingId": property_id,
                "status": ACTIVE_STATUSES,
                "checkInDateFrom": from_date,
                "checkOutDateTo": to_date,
                "limit": 20,
            },
        )
        items = data if isinstance(data, list) else data.get("results", data.get("data", []))
        guests = [g for raw in items if (g := self._parse_reservation(raw))]
        current, next_guest = self._pick_current_and_next(guests) if guests else (None, None)
        return PropertyData(
            property_id=property_id,
            property_name=property_id,
            current_guest=current,
            next_guest=next_guest,
        )

    async def mark_arrived(self, booking_id: str) -> bool:
        await self._put(f"/reservations/{booking_id}/check-in")
        return True

    async def mark_checked_out(self, booking_id: str) -> bool:
        await self._put(f"/reservations/{booking_id}/check-out")
        return True
