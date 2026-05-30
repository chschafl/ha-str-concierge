"""Button platform for STR HA — mark arrived / mark checked out."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import STRCoordinator
from .entity import STREntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: STRCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    property_ids: list[str] = hass.data[DOMAIN][entry.entry_id]["property_ids"]

    entities = []
    for prop_id in property_ids:
        entities.append(MarkArrivedButton(coordinator, prop_id, entry.entry_id))
        entities.append(MarkCheckedOutButton(coordinator, prop_id, entry.entry_id))
    async_add_entities(entities)


class _ActionButton(STREntity, ButtonEntity):
    """Base class for action buttons that target the current booking."""

    async def _current_booking_id(self) -> str:
        pd = self.property_data
        if pd is None or pd.current_guest is None:
            raise HomeAssistantError("No active guest booking to act on")
        return pd.current_guest.booking_id


class MarkArrivedButton(_ActionButton):
    """Button to mark the current guest as arrived."""

    _attr_name = "Mark Guest Arrived"
    _attr_icon = "mdi:account-check"

    def __init__(
        self,
        coordinator: STRCoordinator,
        property_id: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, property_id, entry_id)
        self._attr_unique_id = f"{entry_id}_{property_id}_mark_arrived"

    async def async_press(self) -> None:
        booking_id = await self._current_booking_id()
        try:
            await self.coordinator.provider.mark_arrived(booking_id)
        except NotImplementedError:
            raise HomeAssistantError(
                "The configured provider does not support marking guests as arrived"
            )
        except Exception as err:
            raise HomeAssistantError(f"Failed to mark guest arrived: {err}") from err
        await self.coordinator.async_request_refresh()


class MarkCheckedOutButton(_ActionButton):
    """Button to mark the current guest as checked out."""

    _attr_name = "Mark Guest Checked Out"
    _attr_icon = "mdi:account-arrow-right"

    def __init__(
        self,
        coordinator: STRCoordinator,
        property_id: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, property_id, entry_id)
        self._attr_unique_id = f"{entry_id}_{property_id}_mark_checked_out"

    async def async_press(self) -> None:
        booking_id = await self._current_booking_id()
        try:
            await self.coordinator.provider.mark_checked_out(booking_id)
        except NotImplementedError:
            raise HomeAssistantError(
                "The configured provider does not support marking guests as checked out"
            )
        except Exception as err:
            raise HomeAssistantError(f"Failed to mark guest checked out: {err}") from err
        await self.coordinator.async_request_refresh()
