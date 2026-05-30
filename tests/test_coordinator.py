"""Tests for STRCoordinator — polling and event firing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.str_ha.const import EVENT_GUEST_CHANGED, EVENT_NEXT_GUEST_CHANGED
from custom_components.str_ha.coordinator import STRCoordinator
from custom_components.str_ha.providers.base import Guest, PropertyData

from .conftest import CURRENT_GUEST, NEXT_GUEST, SAMPLE_PROPERTY_DATA


@pytest.fixture
def coordinator(hass, mock_provider):
    return STRCoordinator(
        hass=hass,
        provider=mock_provider,
        property_ids=["prop-001"],
        poll_interval=300,
        entry_id="test-entry",
    )


class TestCoordinatorPolling:
    async def test_first_update_returns_data(self, coordinator, mock_provider):
        await coordinator._async_update_data()
        data = coordinator.data
        assert "prop-001" in data
        assert data["prop-001"].current_guest.booking_id == "booking-001"

    async def test_update_failure_raises(self, coordinator, mock_provider):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_provider.get_property_data.side_effect = RuntimeError("API down")
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


class TestEventFiring:
    async def test_guest_changed_event_fires(self, coordinator, mock_provider, hass):
        await coordinator._async_update_data()

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

        fired_events = []
        hass.bus.async_listen(EVENT_GUEST_CHANGED, lambda e: fired_events.append(e))
        await coordinator._async_update_data()

        assert len(fired_events) == 1
        assert fired_events[0].data["current_guest"] == "Charlie Brown"
        assert fired_events[0].data["previous_guest"] == "Alice Smith"

    async def test_no_event_when_guest_unchanged(self, coordinator, mock_provider, hass):
        await coordinator._async_update_data()

        fired_events = []
        hass.bus.async_listen(EVENT_GUEST_CHANGED, lambda e: fired_events.append(e))
        await coordinator._async_update_data()

        assert len(fired_events) == 0

    async def test_next_guest_changed_event_fires(self, coordinator, mock_provider, hass):
        await coordinator._async_update_data()

        new_next = Guest(
            booking_id="booking-NEXT-NEW",
            name="Dave New",
            checkin=NEXT_GUEST.checkin,
            checkout=NEXT_GUEST.checkout,
        )
        mock_provider.get_property_data.return_value = PropertyData(
            property_id="prop-001",
            property_name="Beach House",
            current_guest=CURRENT_GUEST,
            next_guest=new_next,
        )

        fired = []
        hass.bus.async_listen(EVENT_NEXT_GUEST_CHANGED, lambda e: fired.append(e))
        await coordinator._async_update_data()

        assert len(fired) == 1
        assert fired[0].data["next_guest"] == "Dave New"
