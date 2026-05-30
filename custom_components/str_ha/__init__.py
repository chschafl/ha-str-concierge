"""Short-Term Rental Manager integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CHECKIN_OFFSET_MINUTES,
    CONF_CHECKOUT_OFFSET_MINUTES,
    CONF_KEYMASTER_SLOT,
    CONF_POLL_INTERVAL,
    CONF_PROPERTY_IDS,
    CONF_PROVIDER,
    DEFAULT_CHECKIN_OFFSET_MINUTES,
    DEFAULT_CHECKOUT_OFFSET_MINUTES,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    KEYMASTER_CODE_SLOT_PATTERN,
    KEYMASTER_DATE_END_PATTERN,
    KEYMASTER_DATE_START_PATTERN,
    KEYMASTER_ENABLED_PATTERN,
    PLATFORMS,
)
from .coordinator import STRCoordinator
from .providers import create_provider

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up STR HA from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    provider = create_provider(
        provider_type=entry.data[CONF_PROVIDER],
        api_key=entry.data[CONF_API_KEY],
        base_url=entry.data.get(CONF_BASE_URL),
    )

    property_ids: list[str] = entry.data[CONF_PROPERTY_IDS]
    poll_interval: int = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    coordinator = STRCoordinator(
        hass=hass,
        provider=provider,
        property_ids=property_ids,
        poll_interval=poll_interval,
        entry_id=entry.entry_id,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Could not fetch initial data: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "property_ids": property_ids,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update (e.g. lock offset changes)."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register custom services (idempotent)."""
    if hass.services.has_service(DOMAIN, "sync_keymaster"):
        return

    async def _sync_keymaster(call: ServiceCall) -> None:
        """Write current guest door code and lock window to a keymaster slot."""
        entry_id: str = call.data["entry_id"]
        property_id: str = call.data["property_id"]
        slot: str = call.data["slot"]

        entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if not entry_data:
            _LOGGER.error("sync_keymaster: unknown entry_id %s", entry_id)
            return

        coordinator: STRCoordinator = entry_data["coordinator"]
        entry: ConfigEntry = hass.config_entries.async_get_entry(entry_id)
        pd = coordinator.data.get(property_id) if coordinator.data else None
        guest = pd.current_guest if pd else None

        if not guest:
            _LOGGER.warning("sync_keymaster: no active guest for property %s", property_id)
            return

        checkin_offset = entry.options.get(CONF_CHECKIN_OFFSET_MINUTES, DEFAULT_CHECKIN_OFFSET_MINUTES)
        checkout_offset = entry.options.get(CONF_CHECKOUT_OFFSET_MINUTES, DEFAULT_CHECKOUT_OFFSET_MINUTES)

        from datetime import timedelta
        lock_start = guest.checkin - timedelta(minutes=checkin_offset)
        lock_end = guest.checkout + timedelta(minutes=checkout_offset)

        if guest.door_code:
            pin_entity = KEYMASTER_CODE_SLOT_PATTERN.format(slot=slot)
            await hass.services.async_call(
                "input_text", "set_value",
                {"entity_id": pin_entity, "value": guest.door_code},
            )

        enabled_entity = KEYMASTER_ENABLED_PATTERN.format(slot=slot)
        await hass.services.async_call(
            "input_boolean", "turn_on",
            {"entity_id": enabled_entity},
        )

        start_entity = KEYMASTER_DATE_START_PATTERN.format(slot=slot)
        end_entity = KEYMASTER_DATE_END_PATTERN.format(slot=slot)
        await hass.services.async_call(
            "input_datetime", "set_datetime",
            {"entity_id": start_entity, "datetime": lock_start.isoformat()},
        )
        await hass.services.async_call(
            "input_datetime", "set_datetime",
            {"entity_id": end_entity, "datetime": lock_end.isoformat()},
        )

        _LOGGER.info(
            "Keymaster slot %s updated: pin=%s window=%s–%s",
            slot, guest.door_code, lock_start, lock_end,
        )

    hass.services.async_register(
        DOMAIN,
        "sync_keymaster",
        _sync_keymaster,
        schema=None,
    )
