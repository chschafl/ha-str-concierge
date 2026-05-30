"""Tests for sensor entities — values, lock window calculation."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.str_ha.sensor import LockWindowSensor
from custom_components.str_ha.providers.base import PropertyData

from .conftest import CURRENT_GUEST, NEXT_GUEST


class TestLockWindowSensor:
    def _make_sensor(self, edge, offset_minutes, coordinator=None):
        coord = coordinator or _mock_coordinator()
        sensor = LockWindowSensor(coord, "prop-001", "entry-1", edge, offset_minutes)
        return sensor

    def test_lock_start_is_checkin_minus_offset(self):
        sensor = self._make_sensor("start", 60)
        expected = CURRENT_GUEST.checkin - timedelta(minutes=60)
        assert sensor.native_value == expected

    def test_lock_end_is_checkout_plus_offset(self):
        sensor = self._make_sensor("end", 60)
        expected = CURRENT_GUEST.checkout + timedelta(minutes=60)
        assert sensor.native_value == expected

    def test_lock_start_zero_offset(self):
        sensor = self._make_sensor("start", 0)
        assert sensor.native_value == CURRENT_GUEST.checkin

    def test_lock_end_zero_offset(self):
        sensor = self._make_sensor("end", 0)
        assert sensor.native_value == CURRENT_GUEST.checkout

    def test_lock_start_falls_back_to_next_guest_when_no_current(self):
        coord = _mock_coordinator(current=None, nxt=NEXT_GUEST)
        sensor = self._make_sensor("start", 0, coord)
        assert sensor.native_value == NEXT_GUEST.checkin

    def test_lock_end_is_none_when_no_current_guest(self):
        coord = _mock_coordinator(current=None, nxt=NEXT_GUEST)
        sensor = self._make_sensor("end", 60, coord)
        assert sensor.native_value is None

    def test_extra_state_attributes_contains_offset(self):
        sensor = self._make_sensor("end", 90)
        assert sensor.extra_state_attributes["offset_minutes"] == 90


def _mock_coordinator(current=CURRENT_GUEST, nxt=NEXT_GUEST):
    coord = MagicMock()
    coord.data = {
        "prop-001": PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=current,
            next_guest=nxt,
        )
    }
    return coord
