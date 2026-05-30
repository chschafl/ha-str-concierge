"""Abstract base provider and shared data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Guest:
    """Represents a guest booking. Identity only — lifecycle state is derived
    by the coordinator from booking times + lock events + the local store."""

    booking_id: str
    name: str
    checkin: datetime
    checkout: datetime
    door_code: str | None = None


@dataclass
class Property:
    """Represents a rental property/listing."""

    id: str
    name: str


@dataclass
class PropertyData:
    """Booking data for a single property — what the PMS knows about it."""

    property_id: str
    property_name: str
    current_guest: Guest | None = None
    next_guest: Guest | None = None


class STRProvider(ABC):
    """Abstract base class all backend providers must implement."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url

    @abstractmethod
    async def get_properties(self) -> list[Property]:
        """Return all properties/listings accessible with this credential."""

    @abstractmethod
    async def get_property_data(self, property_id: str) -> PropertyData:
        """Return current and next booking for the given property."""

    # Best-effort write-back. Providers override what they support.
    async def mark_arrived(self, booking_id: str) -> bool:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support mark_arrived"
        )

    async def mark_checked_out(self, booking_id: str) -> bool:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support mark_checked_out"
        )

    @staticmethod
    def _pick_current_and_next(
        bookings: list[Guest],
    ) -> tuple[Guest | None, Guest | None]:
        """Given a list of bookings, return (current, next) by wall-clock time."""
        if not bookings:
            return None, None

        now = datetime.now(bookings[0].checkin.tzinfo)
        active: list[Guest] = []
        upcoming: list[Guest] = []
        for b in bookings:
            if b.checkin <= now <= b.checkout:
                active.append(b)
            elif b.checkin > now:
                upcoming.append(b)

        current = active[0] if active else None
        upcoming.sort(key=lambda g: g.checkin)
        next_guest = upcoming[0] if upcoming else None
        return current, next_guest
