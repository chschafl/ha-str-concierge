"""Button platform: manual overrides and housekeeping workflow actions."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, HOUSE_CLEANING, HOUSE_READY
from .coordinator import STRCoordinator
from .entity import STREntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: STRCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            MarkArrivedButton(coordinator, entry.entry_id),
            MarkDepartedButton(coordinator, entry.entry_id),
            MarkCleaningStartedButton(coordinator, entry.entry_id),
            MarkReadyButton(coordinator, entry.entry_id),
        ]
    )


class MarkArrivedButton(STREntity, ButtonEntity):
    """Manual override when the lock event was missed."""

    _attr_name = "Mark Guest Arrived"
    _attr_icon = "mdi:account-check"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_mark_arrived"

    async def async_press(self) -> None:
        if self.state_data is None or self.state_data.current_guest is None:
            raise HomeAssistantError("No active booking to mark arrived")
        await self.coordinator.async_manual_mark_arrived()


class MarkDepartedButton(STREntity, ButtonEntity):
    """Manual override to force the current guest into the `departed` state."""

    _attr_name = "Mark Guest Departed"
    _attr_icon = "mdi:account-arrow-right"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_mark_departed"

    async def async_press(self) -> None:
        if self.state_data is None or self.state_data.current_guest is None:
            raise HomeAssistantError("No active booking to mark departed")
        await self.coordinator.async_manual_mark_departed()


class MarkCleaningStartedButton(STREntity, ButtonEntity):
    _attr_name = "Mark Cleaning Started"
    _attr_icon = "mdi:broom"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_mark_cleaning_started"

    async def async_press(self) -> None:
        await self.coordinator.async_set_house_state(HOUSE_CLEANING)


class MarkReadyButton(STREntity, ButtonEntity):
    _attr_name = "Mark Ready"
    _attr_icon = "mdi:home-heart"

    def __init__(self, coordinator: STRCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_mark_ready"

    async def async_press(self) -> None:
        await self.coordinator.async_set_house_state(HOUSE_READY)
