"""Tests for sensor entities — values from the merged STRState."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from custom_components.str_ha.coordinator import STRState
from custom_components.str_ha.sensor import (
    GuestNameSensor,
    GuestStatusSensor,
    HouseStateSensor,
    LockAccessEndSensor,
    LockAccessStartSensor,
)

from .conftest import CURRENT_GUEST


def _state(
    *,
    current=CURRENT_GUEST,
    nxt=None,
    guest_status="reserved",
    house_state="ready",
    lock_before_min=60,
    lock_after_min=60,
):
    lock_start = (current.checkin - timedelta(minutes=lock_before_min)) if current else None
    lock_end = (current.checkout + timedelta(minutes=lock_after_min)) if current else None
    return STRState(
        property_id="prop-001",
        property_name="Beach House",
        current_guest=current,
        next_guest=nxt,
        guest_status=guest_status,
        house_state=house_state,
        lock_access_start=lock_start,
        lock_access_end=lock_end,
        entered_at=None,
    )


def _coord(state):
    coord = MagicMock()
    coord.data = state
    coord.property_id = "prop-001"
    return coord


class TestGuestNameSensor:
    def test_returns_current_guest_name(self):
        sensor = GuestNameSensor(_coord(_state()), "entry-1")
        assert sensor.native_value == "Alice Smith"

    def test_returns_none_when_vacant(self):
        sensor = GuestNameSensor(_coord(_state(current=None)), "entry-1")
        assert sensor.native_value is None


class TestGuestStatusSensor:
    def test_passes_through_status(self):
        sensor = GuestStatusSensor(_coord(_state(guest_status="due_in")), "entry-1")
        assert sensor.native_value == "due_in"


class TestHouseStateSensor:
    def test_passes_through_house_state(self):
        sensor = HouseStateSensor(_coord(_state(house_state="dirty")), "entry-1")
        assert sensor.native_value == "dirty"


class TestLockAccessSensors:
    def test_lock_start_is_checkin_minus_offset(self):
        sensor = LockAccessStartSensor(
            _coord(_state(lock_before_min=60)), "entry-1"
        )
        assert sensor.native_value == CURRENT_GUEST.checkin - timedelta(minutes=60)

    def test_lock_end_is_checkout_plus_offset(self):
        sensor = LockAccessEndSensor(
            _coord(_state(lock_after_min=90)), "entry-1"
        )
        assert sensor.native_value == CURRENT_GUEST.checkout + timedelta(minutes=90)

    def test_lock_end_is_none_when_vacant(self):
        sensor = LockAccessEndSensor(_coord(_state(current=None)), "entry-1")
        assert sensor.native_value is None
