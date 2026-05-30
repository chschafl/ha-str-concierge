"""DataUpdateCoordinator for STR HA."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, EVENT_GUEST_CHANGED, EVENT_NEXT_GUEST_CHANGED
from .providers.base import PropertyData, STRProvider

_LOGGER = logging.getLogger(__name__)


class STRCoordinator(DataUpdateCoordinator[dict[str, PropertyData]]):
    """Polls all configured properties and fires HA events on changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        provider: STRProvider,
        property_ids: list[str],
        poll_interval: int,
        entry_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._provider = provider
        self._property_ids = property_ids
        self._entry_id = entry_id
        self._previous: dict[str, PropertyData] = {}

    @property
    def provider(self) -> STRProvider:
        return self._provider

    async def _async_update_data(self) -> dict[str, PropertyData]:
        result: dict[str, PropertyData] = {}

        for prop_id in self._property_ids:
            try:
                data = await self._provider.get_property_data(prop_id)
            except Exception as err:
                raise UpdateFailed(f"Error fetching property {prop_id}: {err}") from err

            result[prop_id] = data
            self._fire_events_if_changed(prop_id, data)

        self._previous = result
        return result

    def _fire_events_if_changed(self, prop_id: str, new: PropertyData) -> None:
        old = self._previous.get(prop_id)
        if old is None:
            return

        old_current_id = old.current_guest.booking_id if old.current_guest else None
        new_current_id = new.current_guest.booking_id if new.current_guest else None
        if old_current_id != new_current_id:
            self.hass.bus.async_fire(
                EVENT_GUEST_CHANGED,
                {
                    "entry_id": self._entry_id,
                    "property_id": prop_id,
                    "property_name": new.property_name,
                    "previous_guest": old.current_guest.name if old.current_guest else None,
                    "current_guest": new.current_guest.name if new.current_guest else None,
                },
            )

        old_next_id = old.next_guest.booking_id if old.next_guest else None
        new_next_id = new.next_guest.booking_id if new.next_guest else None
        if old_next_id != new_next_id:
            self.hass.bus.async_fire(
                EVENT_NEXT_GUEST_CHANGED,
                {
                    "entry_id": self._entry_id,
                    "property_id": prop_id,
                    "property_name": new.property_name,
                    "next_guest": new.next_guest.name if new.next_guest else None,
                },
            )
