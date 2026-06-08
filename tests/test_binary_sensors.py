"""Tests for binary sensor entities."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from custom_components.str_concierge.binary_sensor import (
    GuestPresentSensor,
    LockActiveSensor,
)
from custom_components.str_concierge.coordinator import STRState

from .conftest import CURRENT_GUEST


def _state(
    *,
    current=CURRENT_GUEST,
    guest_status="in_house",
    lock_before_min=60,
    lock_after_min=60,
):
    lock_start = (current.checkin - timedelta(minutes=lock_before_min)) if current else None
    lock_end = (current.checkout + timedelta(minutes=lock_after_min)) if current else None
    return STRState(
        property_id="prop-001",
        property_name="Beach House",
        current_guest=current,
        next_guest=None,
        guest_status=guest_status,
        house_state="occupied",
        lock_access_start=lock_start,
        lock_access_end=lock_end,
        entered_at=None,
    )


def _coord(state):
    coord = MagicMock()
    coord.data = state
    coord.property_id = "prop-001"
    return coord


class TestGuestPresentSensor:
    def test_on_when_in_house(self):
        sensor = GuestPresentSensor(_coord(_state(guest_status="in_house")), "entry-1")
        assert sensor.is_on is True

    def test_off_when_not_in_house(self):
        sensor = GuestPresentSensor(_coord(_state(guest_status="due_in")), "entry-1")
        assert sensor.is_on is False


class TestLockActiveSensor:
    def test_on_inside_window(self):
        # CURRENT_GUEST: checkin 2025-06-01T15:00 .. checkout 2025-06-07T11:00
        # With ±60min offsets, window is 14:00 .. 12:00.
        now = datetime(2025, 6, 3, 12, 0, tzinfo=UTC)
        with patch(
            "custom_components.str_concierge.binary_sensor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = now
            sensor = LockActiveSensor(_coord(_state()), "entry-1")
            assert sensor.is_on is True

    def test_off_before_window(self):
        now = datetime(2025, 5, 31, 12, 0, tzinfo=UTC)
        with patch(
            "custom_components.str_concierge.binary_sensor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = now
            sensor = LockActiveSensor(_coord(_state()), "entry-1")
            assert sensor.is_on is False

    def test_off_after_window(self):
        now = datetime(2025, 6, 8, 12, 0, tzinfo=UTC)
        with patch(
            "custom_components.str_concierge.binary_sensor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = now
            sensor = LockActiveSensor(_coord(_state()), "entry-1")
            assert sensor.is_on is False

    def test_off_when_vacant(self):
        sensor = LockActiveSensor(_coord(_state(current=None)), "entry-1")
        assert sensor.is_on is False
