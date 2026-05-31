"""Tests for STRCoordinator — state derivation, lock latch, departed dwell."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from custom_components.str_concierge.const import (
    DEPARTED_DWELL_SECONDS,
    EVENT_GUEST_CHANGED,
    EVENT_HOUSE_STATE_CHANGED,
    GUEST_DEPARTED,
    GUEST_DUE_IN,
    GUEST_IN_HOUSE,
    GUEST_RESERVED,
    GUEST_VACANT,
    HOUSE_CLEANING,
    HOUSE_DIRTY,
    HOUSE_OCCUPIED,
    HOUSE_READY,
)
from custom_components.str_concierge.coordinator import STRCoordinator
from custom_components.str_concierge.providers.base import Guest, PropertyData

from .conftest import CURRENT_GUEST, NEXT_GUEST, SAMPLE_PROPERTY_DATA


def _utc(year, month, day, hour=12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def coordinator(hass, mock_provider):
    coord = STRCoordinator(
        hass=hass,
        provider=mock_provider,
        property_id="prop-001",
        poll_interval=300,
        entry_id="test-entry",
        arrival_window_hours=4,
        lock_minutes_before_checkin=0,
        lock_minutes_after_checkout=60,
    )
    # Don't hit disk for the storage helper.
    with patch.object(coord, "_persist", return_value=None) as _:
        coord._persist_patched = True
    coord._persist = lambda: _async_noop()
    return coord


async def _async_noop():
    return None


def _at(now: datetime):
    """Patch _now_utc() inside the coordinator module."""
    return patch("custom_components.str_concierge.coordinator._now_utc", return_value=now)


async def _tick(coord, now: datetime):
    """Run one update tick and assign the result to .data (mirrors HA's refresh)."""
    with _at(now):
        coord.data = await coord._async_update_data()
    return coord.data


class TestCoordinatorPolling:
    async def test_first_update_returns_state(self, coordinator, mock_provider):
        await _tick(coordinator, _utc(2025, 5, 1))
        assert coordinator.data is not None
        assert coordinator.data.current_guest.booking_id == "booking-001"

    async def test_update_failure_raises(self, coordinator, mock_provider):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_provider.get_property_data.side_effect = RuntimeError("API down")
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


class TestGuestStateDerivation:
    async def test_reserved_when_far_before_checkin(self, coordinator):
        await _tick(coordinator, _utc(2025, 5, 25))
        assert coordinator.data.guest_status == GUEST_RESERVED

    async def test_due_in_inside_arrival_window(self, coordinator):
        # 2h before check-in; arrival window is 4h.
        await _tick(coordinator, _utc(2025, 6, 1, hour=13))
        assert coordinator.data.guest_status == GUEST_DUE_IN

    async def test_in_house_after_lock_event(self, coordinator):
        await _tick(coordinator, _utc(2025, 6, 1, hour=14))
        with _at(_utc(2025, 6, 1, hour=16)):
            await coordinator.async_handle_lock_unlocked()
        await _tick(coordinator, _utc(2025, 6, 1, hour=16))
        assert coordinator.data.guest_status == GUEST_IN_HOUSE
        assert coordinator.data.house_state == HOUSE_OCCUPIED

    async def test_lock_event_outside_window_is_ignored(self, coordinator):
        await _tick(coordinator, _utc(2025, 5, 25))
        with _at(_utc(2025, 5, 25)):
            await coordinator.async_handle_lock_unlocked()
        await _tick(coordinator, _utc(2025, 5, 25))
        assert coordinator.data.guest_status == GUEST_RESERVED

    async def test_departed_when_past_lock_end_after_arrival(self, coordinator):
        await _tick(coordinator, _utc(2025, 6, 5))
        with _at(_utc(2025, 6, 5)):
            await coordinator.async_handle_lock_unlocked()
        # Jump past checkout (2025-06-07 11:00) + 60min courtesy.
        await _tick(coordinator, _utc(2025, 6, 7, hour=13))
        assert coordinator.data.guest_status == GUEST_DEPARTED

    async def test_vacant_when_no_current_guest(self, coordinator, mock_provider):
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=None,
        )
        await _tick(coordinator, _utc(2025, 5, 1))
        assert coordinator.data.guest_status == GUEST_VACANT

    async def test_next_guest_promoted_to_current_inside_arrival_window(
        self, coordinator, mock_provider
    ):
        """PMS only marks bookings 'current' between checkin and checkout.
        Inside the arrival window we promote next → current so the entities
        populate and status flips to due_in."""
        upcoming = Guest(
            booking_id="booking-NEXT",
            name="Kaite Sambrook",
            checkin=_utc(2025, 6, 1, hour=15),   # check-in in 2 hours
            checkout=_utc(2025, 6, 3, hour=11),
        )
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=upcoming,
        )
        # arrival_window_hours=4 (set in the fixture); 2h before checkin → in window.
        await _tick(coordinator, _utc(2025, 6, 1, hour=13))
        assert coordinator.data.current_guest is not None
        assert coordinator.data.current_guest.name == "Kaite Sambrook"
        assert coordinator.data.guest_status == GUEST_DUE_IN

    async def test_next_guest_promoted_even_when_far_in_future(
        self, coordinator, mock_provider
    ):
        """Hosts always want to see who's coming next, even months away.
        We promote next → current and report `reserved`, not `vacant`."""
        upcoming = Guest(
            booking_id="booking-NEXT",
            name="Kaite Sambrook",
            checkin=_utc(2025, 6, 5, hour=15),   # check-in 4+ days away
            checkout=_utc(2025, 6, 7, hour=11),
        )
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=upcoming,
        )
        await _tick(coordinator, _utc(2025, 6, 1, hour=12))
        assert coordinator.data.current_guest is not None
        assert coordinator.data.current_guest.name == "Kaite Sambrook"
        assert coordinator.data.guest_status == GUEST_RESERVED


class TestHouseState:
    async def test_house_state_defaults_to_ready(self, coordinator):
        await _tick(coordinator, _utc(2025, 5, 1))
        assert coordinator.data.house_state == HOUSE_READY

    async def test_house_flips_to_occupied_on_in_house(self, coordinator):
        await _tick(coordinator, _utc(2025, 6, 1, hour=16))
        with _at(_utc(2025, 6, 1, hour=16)):
            await coordinator.async_handle_lock_unlocked()
        await _tick(coordinator, _utc(2025, 6, 1, hour=16))
        assert coordinator.data.house_state == HOUSE_OCCUPIED

    async def test_manual_house_state_transitions(self, coordinator):
        await _tick(coordinator, _utc(2025, 5, 1))
        with _at(_utc(2025, 5, 1)):
            await coordinator.async_set_house_state(HOUSE_DIRTY)
        await _tick(coordinator, _utc(2025, 5, 1))
        assert coordinator.data.house_state == HOUSE_DIRTY

        with _at(_utc(2025, 5, 1)):
            await coordinator.async_set_house_state(HOUSE_CLEANING)
        await _tick(coordinator, _utc(2025, 5, 1))
        assert coordinator.data.house_state == HOUSE_CLEANING


class TestEventFiring:
    async def test_guest_changed_event_fires(
        self, coordinator, mock_provider, hass
    ):
        await _tick(coordinator, _utc(2025, 6, 5))

        new_guest = Guest(
            booking_id="booking-NEW",
            name="Charlie Brown",
            checkin=CURRENT_GUEST.checkin,
            checkout=CURRENT_GUEST.checkout,
        )
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=new_guest,
            next_guest=NEXT_GUEST,
        )

        fired = []
        hass.bus.async_listen(EVENT_GUEST_CHANGED, lambda e: fired.append(e))
        await _tick(coordinator, _utc(2025, 6, 5))
        await hass.async_block_till_done()

        assert any(e.data["current_guest"] == "Charlie Brown" for e in fired)

    async def test_house_state_event_fires_on_change(self, coordinator, hass):
        await _tick(coordinator, _utc(2025, 5, 1))
        fired = []
        hass.bus.async_listen(EVENT_HOUSE_STATE_CHANGED, lambda e: fired.append(e))
        with _at(_utc(2025, 5, 1)):
            await coordinator.async_set_house_state(HOUSE_DIRTY)
        await _tick(coordinator, _utc(2025, 5, 1))
        await hass.async_block_till_done()
        assert any(e.data["state"] == HOUSE_DIRTY for e in fired)
