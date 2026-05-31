"""Host Tools provider.

API base: ``https://app.hosttools.com/api`` (no ``/v1`` path segment)
Authentication: custom header ``authToken: <token>`` — **not** ``Authorization: Bearer``.

Key endpoints used:
  GET /getListings
      → all listings accessible with this token
  GET /getReservations/{listingId}/{startDate}/{endDate}
      → list of reservations whose [checkIn, checkOut] overlaps the window

Reservation fields we care about (with fallback aliases — Host Tools is
inconsistent across endpoints and integration sources):

    _id / id / confirmationCode          → booking_id
    guestFirstName + guestLastName       → name (also: firstName + lastName)
    checkIn / startDate                  → checkin DATE
    checkInTime / checkin_time           → checkin TIME of day (numeric hour
                                           like 16, "HH:MM", "4 PM", etc.).
                                           Combined with the date above.
    checkOut / endDate                   → checkout DATE
    checkOutTime / checkout_time         → checkout TIME of day
    lockCode / doorCode / door_code      → door_code (lockCode is the
        / accessCode                       canonical Host Tools field)
    status / reservationStatus           → filter; we keep only "accepted",
                                           "confirmed", "pending", "inquiry"
                                           and skip "cancelled", "canceled",
                                           "declined", "blocked"

Listing fields:
    _id / id / listingId                 → property_id
    nickname / name / title              → property_name

The Host Tools API also has a ``POST /setreservation/{id}`` endpoint for
updating door codes / guidebook URLs, but does not have an "advance the
reservation status to arrived/checked-out" concept that maps to our
``mark_arrived`` / ``mark_checked_out``. We therefore inherit the base
class's ``NotImplementedError`` for those — the integration's local state
remains the source of truth for guest lifecycle.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.util import dt as dt_util

from .base import Guest, Property, PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://app.hosttools.com/api"

# Captures a still-active checkout from earlier today.
LOOKBACK = timedelta(days=1)

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


def _parse_time_of_day(value) -> tuple[int, int] | None:
    """Return (hour, minute) from a Host Tools time field.

    Accepts numeric (16 → 16:00, 16.5 → 16:30), bare digits ("16" → 16:00),
    24-hour ("16:00"), 12-hour ("4:00 PM" / "4 PM"), or an ISO timestamp
    (pulls the HH:MM portion). Returns None when the value is unparseable.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None  # bool is a subclass of int — exclude explicitly
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        h = int(value)
        m = round((float(value) - h) * 60)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
        return None

    s = str(value).strip()
    if not s:
        return None

    # Bare numeric string like "16"
    if re.fullmatch(r"\d{1,2}", s):
        h = int(s)
        if 0 <= h <= 23:
            return h, 0

    # 24-hour "HH:MM" or "H:MM"
    m24 = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m24:
        h, mm = int(m24.group(1)), int(m24.group(2))
        if 0 <= h <= 23 and 0 <= mm <= 59:
            return h, mm

    # 12-hour "h:mm AM/PM" or "h AM/PM"
    m12 = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([APap][Mm])", s)
    if m12:
        h = int(m12.group(1))
        mm = int(m12.group(2)) if m12.group(2) else 0
        ampm = m12.group(3).upper()
        if 1 <= h <= 12 and 0 <= mm <= 59:
            if ampm == "PM" and h < 12:
                h += 12
            elif ampm == "AM" and h == 12:
                h = 0
            return h, mm

    # ISO timestamp — pull "T HH:MM"
    iso = re.search(r"T(\d{2}):(\d{2})", s)
    if iso:
        return int(iso.group(1)), int(iso.group(2))

    return None


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _combine_date_and_time(date_value, time_value) -> datetime | None:
    """Combine a date (or ISO datetime) with a separate time-of-day field.

    Host Tools sends ``checkIn`` as a date-only string (``"2026-06-01"``) and
    ``checkInTime`` separately as ``16``, ``"16:00"``, ``"4 PM"``, etc. The
    time-of-day value refers to **local wall-clock time at the property** —
    in practice, HA's configured timezone. We attach that local timezone
    when combining, then convert the result to UTC for downstream storage.

    Branches:

    * ``date_value`` is just a date (``YYYY-MM-DD``)
        → build a naive datetime, attach HA's local timezone, convert to UTC.
        → if no time field is present, default to midnight local time.
    * ``date_value`` is a full ISO timestamp with embedded time/offset
        → trust the embedded offset; if a separate time field is present,
          override the hour/minute portion in that same zone (Host Tools
          rarely sends both, but we handle it for symmetry).
    """
    raw = "" if date_value is None else str(date_value).strip()
    if not raw:
        return None

    time_of_day = _parse_time_of_day(time_value)

    if _DATE_ONLY_RE.match(raw):
        try:
            naive = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None
        h, m = time_of_day if time_of_day is not None else (0, 0)
        # dt_util.DEFAULT_TIME_ZONE follows HA's user-configured timezone.
        tz = dt_util.DEFAULT_TIME_ZONE
        local = naive.replace(
            hour=h, minute=m, second=0, microsecond=0, tzinfo=tz,
        )
        result = local.astimezone(timezone.utc)
        _LOGGER.debug(
            "combine date+time: date=%r time=%r tz=%s → local=%s → utc=%s",
            raw, time_value, tz, local.isoformat(), result.isoformat(),
        )
        return result

    base = _parse_dt(raw)
    if base is None:
        return None
    if time_of_day is not None:
        h, m = time_of_day
        base = base.replace(hour=h, minute=m, second=0, microsecond=0)
    return base


class HostToolsProvider(STRProvider):
    """Provider backed by the Host Tools public API."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        lookahead_days: int = 30,
    ) -> None:
        super().__init__(api_key, base_url or BASE_URL)
        self._lookahead = timedelta(days=lookahead_days)

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
        data = await self._get("/getListings")
        items = (
            data
            if isinstance(data, list)
            else data.get("listings", data.get("data", []))
        )
        return [p for raw in items if (p := self._parse_listing(raw)) is not None]

    async def get_property_data(self, property_id: str) -> PropertyData:
        now = datetime.now(timezone.utc)
        start = _ymd(now - LOOKBACK)
        end = _ymd(now + self._lookahead)
        data = await self._get(f"/getReservations/{property_id}/{start}/{end}")

        items = (
            data
            if isinstance(data, list)
            else data.get("reservations", data.get("data", []))
        )

        guests = [g for raw in items if (g := self._parse_reservation(raw)) is not None]
        skipped = len(items) - len(guests)
        _LOGGER.info(
            "Host Tools /getReservations[%s, %s..%s]: %d returned, %d kept, %d filtered",
            property_id,
            start,
            end,
            len(items),
            len(guests),
            skipped,
        )

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
    def _parse_listing(raw: dict) -> Property | None:
        listing_id = _first(raw, ["_id", "id", "listingId"])
        if not listing_id:
            return None
        name = _first(raw, ["nickname", "name", "title"], str(listing_id))
        return Property(id=str(listing_id), name=str(name))

    @staticmethod
    def _parse_reservation(raw: dict) -> Guest | None:
        status = (
            str(_first(raw, ["status", "reservationStatus"], "accepted"))
            .lower()
            .strip()
        )
        if status in SKIP_STATUSES or status not in ACTIVE_STATUSES:
            _LOGGER.debug(
                "Skipping reservation %s (status=%s)",
                _first(raw, ["_id", "id", "confirmationCode"]),
                status,
            )
            return None

        booking_id = _first(raw, ["_id", "id", "confirmationCode", "confirmation_code"])

        # Host Tools sends date and time-of-day as separate fields:
        # checkIn = "2026-06-01" (date only), checkInTime = 16 (4pm).
        # Combine them so the integration's status/lock-window calculations
        # use the real arrival/departure clock time.
        checkin = _combine_date_and_time(
            _first(raw, ["checkIn", "startDate", "start_date"]),
            _first(raw, ["checkInTime", "checkin_time", "startTime"]),
        )
        checkout = _combine_date_and_time(
            _first(raw, ["checkOut", "endDate", "end_date"]),
            _first(raw, ["checkOutTime", "checkout_time", "endTime"]),
        )

        if not all([booking_id, checkin, checkout]):
            _LOGGER.debug("Skipping incomplete reservation: %s", raw)
            return None

        first = _first(raw, ["guestFirstName", "firstName"], "")
        last = _first(raw, ["guestLastName", "lastName"], "")
        name = f"{first} {last}".strip() or _first(
            raw, ["guestName", "name"], "Unknown"
        )

        # `lockCode` is the field name Host Tools actually uses; doorCode /
        # door_code / accessCode are kept as defensive aliases for variant
        # payloads and historical/integration responses.
        door_code = _first(
            raw, ["lockCode", "doorCode", "door_code", "accessCode", "access_code"]
        )
        if not door_code:
            _LOGGER.debug(
                "Reservation %s parsed without a door code — raw keys: %s",
                booking_id,
                sorted(raw.keys()),
            )

        return Guest(
            booking_id=str(booking_id),
            name=name,
            checkin=checkin,
            checkout=checkout,
            door_code=door_code,
        )
