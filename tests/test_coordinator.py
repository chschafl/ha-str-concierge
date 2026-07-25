"""Tests for STRCoordinator — state derivation, lock latch, departed dwell."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from custom_components.str_concierge.const import (
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

from .conftest import CURRENT_GUEST, NEXT_GUEST


def _utc(year, month, day, hour=12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


@pytest.fixture
def coordinator(hass, mock_provider):
    coord = STRCoordinator(
        hass=hass,
        provider=mock_provider,
        property_id="prop-001",
        poll_interval=300,
        entry_id="test-entry",
        arrival_window_minutes=240,
        vacancy_threshold_days=30,
        lock_minutes_before_checkin=0,
        lock_minutes_after_checkout=60,
        property_name="Beach House",
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

    async def test_previous_guest_kept_during_checkout_grace(
        self, coordinator, mock_provider
    ):
        """PMS providers drop a booking the instant checkout passes. We hold
        the previous guest (and their door code) in place until the
        post-checkout grace window elapses."""
        # Initial tick: A is current; latch arrival via lock unlock.
        await _tick(coordinator, _utc(2025, 6, 5))
        with _at(_utc(2025, 6, 5)):
            await coordinator.async_handle_lock_unlocked()
        await _tick(coordinator, _utc(2025, 6, 5))

        # Provider rotates A out — only the next booking is surfaced now.
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=NEXT_GUEST,
        )

        # A's checkout is 06-07 11:00; lock_after=60 → grace until 12:00.
        in_grace = _utc(2025, 6, 7, hour=11) + timedelta(minutes=30)
        await _tick(coordinator, in_grace)
        assert coordinator.data.current_guest.booking_id == "booking-001"
        assert coordinator.data.current_guest.door_code == "1234"
        assert coordinator.data.guest_status == GUEST_IN_HOUSE

    async def test_guest_still_shown_45_minutes_after_checkout(
        self, coordinator, mock_provider
    ):
        """Reproduces the reported issue: checkout is 11:00, it's currently
        11:45 (well inside the 60-minute grace window configured in the
        `coordinator` fixture) — the checked-out guest must still be shown,
        not the next guest, even though the PMS has already dropped the
        booking from `current`."""
        await _tick(coordinator, _utc(2025, 6, 5))

        # PMS-side checkout has happened: current slot is empty, next guest surfaces.
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=NEXT_GUEST,
        )

        # Alice's checkout is 2025-06-07 11:00; it is now 11:45 — 45 minutes
        # later, still short of the 60-minute grace window.
        forty_five_min_after_checkout = _utc(2025, 6, 7, hour=11) + timedelta(minutes=45)
        await _tick(coordinator, forty_five_min_after_checkout)

        assert coordinator.data.current_guest is not None
        assert coordinator.data.current_guest.booking_id == CURRENT_GUEST.booking_id
        assert coordinator.data.current_guest.name == CURRENT_GUEST.name
        assert coordinator.data.current_guest.door_code == CURRENT_GUEST.door_code
        assert coordinator.data.current_guest.booking_id != NEXT_GUEST.booking_id

    async def test_rotates_to_next_guest_after_grace_ends(
        self, coordinator, mock_provider
    ):
        """Past `checkout + lock_after`, the next guest takes over (here with
        no lock latch, so the dwell timer isn't involved)."""
        await _tick(coordinator, _utc(2025, 6, 5))
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=NEXT_GUEST,
        )

        # During grace: A still current.
        in_grace = _utc(2025, 6, 7, hour=11) + timedelta(minutes=30)
        await _tick(coordinator, in_grace)
        assert coordinator.data.current_guest.booking_id == "booking-001"

        # Past grace: B promoted, door code follows.
        past_grace = _utc(2025, 6, 7, hour=12) + timedelta(minutes=1)
        await _tick(coordinator, past_grace)
        assert coordinator.data.current_guest.booking_id == "booking-002"
        assert coordinator.data.current_guest.door_code == "5678"

    async def test_arrived_guest_survives_pms_hiccup_before_checkout(
        self, coordinator, mock_provider
    ):
        """Reproduces the reported bug: right after a guest checks in, a
        transient/reordered PMS response (e.g. immediately after our own
        `mark_arrived` write) reports the booking as gone and surfaces
        `next_guest` in its place — mid-stay, well before checkout. The
        already-arrived guest must not be evicted by a single bad poll."""
        # Mid-stay: A is current; latch arrival via lock unlock.
        await _tick(coordinator, _utc(2025, 6, 5))
        with _at(_utc(2025, 6, 5)):
            await coordinator.async_handle_lock_unlocked()
        await _tick(coordinator, _utc(2025, 6, 5))
        assert coordinator.data.entered_at is not None

        # PMS hiccup: current slot empty, next guest surfaces — well before
        # A's checkout (2025-06-07 11:00).
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=NEXT_GUEST,
        )
        await _tick(coordinator, _utc(2025, 6, 5, hour=18))

        assert coordinator.data.current_guest is not None
        assert coordinator.data.current_guest.booking_id == CURRENT_GUEST.booking_id
        assert coordinator.data.guest_status == GUEST_IN_HOUSE

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

    async def test_next_guest_promoted_within_vacancy_threshold(
        self, coordinator, mock_provider
    ):
        """Hosts always want to see who's coming next — as long as they're
        inside the vacancy threshold (default 30 days)."""
        upcoming = Guest(
            booking_id="booking-NEXT",
            name="Kaite Sambrook",
            checkin=_utc(2025, 6, 5, hour=15),   # 4+ days out, well within 30
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

    async def test_vacant_when_next_guest_beyond_vacancy_threshold(
        self, coordinator, mock_provider
    ):
        """A booking past the vacancy threshold (default 30 days) must NOT
        be promoted — status stays vacant until it gets closer."""
        far_off = Guest(
            booking_id="booking-FAR",
            name="Future Guest",
            checkin=_utc(2025, 12, 1, hour=15),   # 6+ months out
            checkout=_utc(2025, 12, 5, hour=11),
        )
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=None,
            next_guest=far_off,
        )
        await _tick(coordinator, _utc(2025, 6, 1, hour=12))
        assert coordinator.data.current_guest is None
        assert coordinator.data.guest_status == GUEST_VACANT


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
