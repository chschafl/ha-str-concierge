"""Tests for the base data models and _pick_current_and_next logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.str_ha.providers.base import Guest, PropertyData, STRProvider


def _guest(booking_id: str, offset_hours_start: int, offset_hours_end: int) -> Guest:
    now = datetime.now(timezone.utc)
    return Guest(
        booking_id=booking_id,
        name=f"Guest {booking_id}",
        checkin=now + timedelta(hours=offset_hours_start),
        checkout=now + timedelta(hours=offset_hours_end),
    )


class TestPickCurrentAndNext:
    def test_active_booking_is_current(self):
        active = _guest("a", -2, 5)  # started 2h ago, ends in 5h
        upcoming = _guest("b", 24, 48)
        current, nxt = STRProvider._pick_current_and_next([active, upcoming])
        assert current.booking_id == "a"
        assert nxt.booking_id == "b"

    def test_no_active_booking_returns_none_current(self):
        upcoming = _guest("b", 24, 48)
        current, nxt = STRProvider._pick_current_and_next([upcoming])
        assert current is None
        assert nxt.booking_id == "b"

    def test_next_is_soonest_upcoming(self):
        soon = _guest("soon", 10, 20)
        later = _guest("later", 50, 70)
        _, nxt = STRProvider._pick_current_and_next([later, soon])
        assert nxt.booking_id == "soon"

    def test_empty_list_returns_none_none(self):
        pd = PropertyData(property_id="x", property_name="X")
        assert pd.current_guest is None
        assert pd.next_guest is None


