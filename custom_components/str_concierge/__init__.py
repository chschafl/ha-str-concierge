"""STR Concierge integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_API_KEY,
    CONF_ARRIVAL_WINDOW_MINUTES,
    CONF_BASE_URL,
    CONF_CLEANER_KEYMASTER_SLOT,
    CONF_KEYMASTER_SLOT,
    CONF_LOCK_ENTITY_ID,
    CONF_LOCK_MINUTES_AFTER_CHECKOUT,
    CONF_LOCK_MINUTES_BEFORE_CHECKIN,
    CONF_LOCK_TRIGGER_SOURCE,
    CONF_LOCK_UNLOCK_STATES,
    CONF_POLL_INTERVAL,
    CONF_PROPERTY_ID,
    CONF_PROPERTY_NAME,
    CONF_PROVIDER,
    CONF_VACANCY_THRESHOLD_DAYS,
    DEFAULT_ARRIVAL_WINDOW_MINUTES,
    DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT,
    DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN,
    DEFAULT_LOCK_TRIGGER_SOURCE,
    DEFAULT_LOCK_UNLOCK_STATES,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VACANCY_THRESHOLD_DAYS,
    DOMAIN,
    KEYMASTER_CODE_SLOT_PATTERN,
    KEYMASTER_DATE_END_PATTERN,
    KEYMASTER_DATE_START_PATTERN,
    KEYMASTER_ENABLED_PATTERN,
    KEYMASTER_LOCK_EVENT,
    LOCK_TRIGGER_DISABLED,
    LOCK_TRIGGER_ENTITY,
    LOCK_TRIGGER_KEYMASTER,
    PLATFORMS,
)
from .coordinator import STRCoordinator
from .providers import create_provider

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up STR Concierge from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    options = entry.options

    # Backward-compat: earlier versions stored arrival window in hours.
    arrival_minutes = options.get(CONF_ARRIVAL_WINDOW_MINUTES)
    if arrival_minutes is None:
        legacy_hours = options.get("arrival_window_hours")
        arrival_minutes = (
            legacy_hours * 60 if legacy_hours is not None else DEFAULT_ARRIVAL_WINDOW_MINUTES
        )

    vacancy_threshold_days = options.get(
        CONF_VACANCY_THRESHOLD_DAYS, DEFAULT_VACANCY_THRESHOLD_DAYS
    )

    provider = create_provider(
        provider_type=entry.data[CONF_PROVIDER],
        api_key=entry.data[CONF_API_KEY],
        base_url=entry.data.get(CONF_BASE_URL),
        lookahead_days=vacancy_threshold_days,
    )

    property_id: str = entry.data[CONF_PROPERTY_ID]
    # Picked during the config flow; falls back to the ID for old entries
    # that predate CONF_PROPERTY_NAME.
    property_name: str = entry.data.get(CONF_PROPERTY_NAME, property_id)
    poll_interval: int = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    coordinator = STRCoordinator(
        hass=hass,
        provider=provider,
        property_id=property_id,
        property_name=property_name,
        poll_interval=poll_interval,
        entry_id=entry.entry_id,
        arrival_window_minutes=arrival_minutes,
        vacancy_threshold_days=vacancy_threshold_days,
        lock_minutes_before_checkin=options.get(
            CONF_LOCK_MINUTES_BEFORE_CHECKIN, DEFAULT_LOCK_MINUTES_BEFORE_CHECKIN
        ),
        lock_minutes_after_checkout=options.get(
            CONF_LOCK_MINUTES_AFTER_CHECKOUT, DEFAULT_LOCK_MINUTES_AFTER_CHECKOUT
        ),
    )

    await coordinator.async_load_store()

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Could not fetch initial data: {err}") from err

    unsubscribers = _install_lock_listener(hass, entry, coordinator)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "property_id": property_id,
        "unsubscribers": unsubscribers,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry_data:
            for unsub in entry_data.get("unsubscribers", []):
                unsub()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change (lock window, arrival window, trigger source)."""
    await hass.config_entries.async_reload(entry.entry_id)


def _install_lock_listener(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: STRCoordinator
) -> list:
    """Install the configured lock-event listener. Returns unsubscriber callables."""
    options = entry.options
    source = options.get(CONF_LOCK_TRIGGER_SOURCE, DEFAULT_LOCK_TRIGGER_SOURCE)
    unsubs: list = []

    # Cleaner keymaster slot is always installed regardless of the main lock
    # trigger source — they're independent concerns.
    cleaner_slot = options.get(CONF_CLEANER_KEYMASTER_SLOT, "").strip()
    if cleaner_slot:
        @callback
        def _on_cleaner_event(event: Event) -> None:
            data = event.data
            event_slot = (
                data.get("code_slot_name")
                or data.get("slot_name")
                or data.get("slot")
            )
            action = (data.get("action_text") or data.get("action") or "").lower()
            if event_slot != cleaner_slot:
                return
            if action and "unlock" not in action and "keypad" not in action:
                return
            hass.async_create_task(coordinator.async_handle_cleaner_arrived())

        unsubs.append(
            hass.bus.async_listen(KEYMASTER_LOCK_EVENT, _on_cleaner_event)
        )

    if source == LOCK_TRIGGER_DISABLED:
        _LOGGER.debug(
            "Guest lock trigger disabled — arrival latching only via manual buttons"
        )
        return unsubs

    if source == LOCK_TRIGGER_KEYMASTER:
        slot = options.get(CONF_KEYMASTER_SLOT, "").strip()
        if not slot:
            _LOGGER.warning(
                "Keymaster lock trigger selected but no slot configured; "
                "lock-based arrivals disabled"
            )
            return unsubs

        @callback
        def _on_keymaster_event(event: Event) -> None:
            data = event.data
            event_slot = (
                data.get("code_slot_name")
                or data.get("slot_name")
                or data.get("slot")
            )
            action = (data.get("action_text") or data.get("action") or "").lower()
            if event_slot != slot:
                return
            if action and "unlock" not in action and "keypad" not in action:
                return
            hass.async_create_task(coordinator.async_handle_lock_unlocked())

        unsubs.append(hass.bus.async_listen(KEYMASTER_LOCK_EVENT, _on_keymaster_event))

    elif source == LOCK_TRIGGER_ENTITY:
        entity_id = options.get(CONF_LOCK_ENTITY_ID, "").strip()
        if not entity_id:
            _LOGGER.warning(
                "Entity lock trigger selected but no entity configured; "
                "lock-based arrivals disabled"
            )
            return unsubs
        unlock_states = options.get(CONF_LOCK_UNLOCK_STATES, DEFAULT_LOCK_UNLOCK_STATES)
        if isinstance(unlock_states, str):
            unlock_states = [s.strip() for s in unlock_states.split(",") if s.strip()]

        @callback
        def _on_state_change(event: Event) -> None:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            if new_state is None:
                return
            if new_state.state not in unlock_states:
                return
            if old_state is not None and old_state.state == new_state.state:
                return
            hass.async_create_task(coordinator.async_handle_lock_unlocked())

        unsubs.append(
            async_track_state_change_event(hass, [entity_id], _on_state_change)
        )

    return unsubs


def _register_services(hass: HomeAssistant) -> None:
    """Register the keymaster-sync service (idempotent)."""
    if hass.services.has_service(DOMAIN, "sync_keymaster"):
        return

    async def _sync_keymaster(call: ServiceCall) -> None:
        entry_id: str = call.data["entry_id"]
        slot: str = call.data["slot"]

        entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if not entry_data:
            _LOGGER.error("sync_keymaster: unknown entry_id %s", entry_id)
            return

        coordinator: STRCoordinator = entry_data["coordinator"]
        state = coordinator.data
        guest = state.current_guest if state else None
        if not guest:
            _LOGGER.warning("sync_keymaster: no active guest")
            return

        lock_start = state.lock_access_start
        lock_end = state.lock_access_end

        if guest.door_code:
            await hass.services.async_call(
                "input_text",
                "set_value",
                {
                    "entity_id": KEYMASTER_CODE_SLOT_PATTERN.format(slot=slot),
                    "value": guest.door_code,
                },
            )
        await hass.services.async_call(
            "input_boolean",
            "turn_on",
            {"entity_id": KEYMASTER_ENABLED_PATTERN.format(slot=slot)},
        )
        if lock_start is not None:
            await hass.services.async_call(
                "input_datetime",
                "set_datetime",
                {
                    "entity_id": KEYMASTER_DATE_START_PATTERN.format(slot=slot),
                    "datetime": lock_start.isoformat(),
                },
            )
        if lock_end is not None:
            await hass.services.async_call(
                "input_datetime",
                "set_datetime",
                {
                    "entity_id": KEYMASTER_DATE_END_PATTERN.format(slot=slot),
                    "datetime": lock_end.isoformat(),
                },
            )

        _LOGGER.info(
            "Keymaster slot %s synced (pin set=%s window=%s–%s)",
            slot,
            bool(guest.door_code),
            lock_start,
            lock_end,
        )

    hass.services.async_register(DOMAIN, "sync_keymaster", _sync_keymaster, schema=None)
