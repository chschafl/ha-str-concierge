"""Config flow for STR HA."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

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
    PROVIDER_CUSTOM,
    PROVIDER_GUESTY,
    PROVIDER_HOST_TOOLS,
    PROVIDER_HOSTFULLY,
    PROVIDER_OPTIONS,
)
from .providers import create_provider

_LOGGER = logging.getLogger(__name__)

_PROVIDER_LABELS = {
    PROVIDER_HOST_TOOLS: "Host Tools",
    PROVIDER_CUSTOM: "Custom Endpoint",
    PROVIDER_HOSTFULLY: "Hostfully",
    PROVIDER_GUESTY: "Guesty",
}

_NEEDS_BASE_URL = {PROVIDER_CUSTOM}


class STRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step config flow: provider → credentials → properties."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider: str | None = None
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._available_properties: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_credentials()

        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER): vol.In(
                    {k: _PROVIDER_LABELS[k] for k in PROVIDER_OPTIONS}
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            self._base_url = user_input.get(CONF_BASE_URL)

            try:
                provider = create_provider(
                    self._provider, self._api_key, self._base_url
                )
                props = await provider.get_properties()
            except Exception as err:
                _LOGGER.debug("Credential validation error: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._available_properties = [
                    {"id": p.id, "name": p.name} for p in props
                ]
                return await self.async_step_properties()

        needs_url = self._provider in _NEEDS_BASE_URL
        schema_dict: dict = {
            vol.Required(CONF_API_KEY): str,
        }
        if needs_url:
            schema_dict[vol.Required(CONF_BASE_URL)] = str
        elif self._provider == PROVIDER_GUESTY:
            schema_dict[vol.Optional(CONF_BASE_URL)] = str

        description_placeholders = {}
        if self._provider == PROVIDER_GUESTY:
            description_placeholders["api_key_hint"] = "Format: client_id:client_secret"
        elif self._provider == PROVIDER_HOSTFULLY:
            description_placeholders["api_key_hint"] = "Your Hostfully API key"
        else:
            description_placeholders["api_key_hint"] = "Your API token / key"

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_properties(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            selected: list[str] = user_input[CONF_PROPERTY_IDS]
            if not selected:
                errors[CONF_PROPERTY_IDS] = "no_properties_selected"
            else:
                return self.async_create_entry(
                    title=self._entry_title(),
                    data={
                        CONF_PROVIDER: self._provider,
                        CONF_API_KEY: self._api_key,
                        CONF_BASE_URL: self._base_url,
                        CONF_PROPERTY_IDS: selected,
                        CONF_POLL_INTERVAL: user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    },
                    options={
                        CONF_CHECKIN_OFFSET_MINUTES: DEFAULT_CHECKIN_OFFSET_MINUTES,
                        CONF_CHECKOUT_OFFSET_MINUTES: DEFAULT_CHECKOUT_OFFSET_MINUTES,
                    },
                )

        prop_choices = {p["id"]: p["name"] for p in self._available_properties}
        if not prop_choices:
            return self.async_abort(reason="no_properties")

        import homeassistant.helpers.config_validation as cv
        schema = vol.Schema(
            {
                vol.Required(CONF_PROPERTY_IDS): vol.All(
                    cv.ensure_list,
                    [vol.In(prop_choices)],
                ),
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
                    int, vol.Range(min=60, max=3600)
                ),
            }
        )
        return self.async_show_form(
            step_id="properties",
            data_schema=schema,
            errors=errors,
        )

    def _entry_title(self) -> str:
        provider_label = _PROVIDER_LABELS.get(self._provider, self._provider)
        if self._base_url:
            return f"{provider_label} ({self._base_url})"
        return provider_label

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return STROptionsFlow(config_entry)


class STROptionsFlow(config_entries.OptionsFlow):
    """Allow users to edit lock offsets and keymaster slot after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CHECKIN_OFFSET_MINUTES,
                    default=current.get(CONF_CHECKIN_OFFSET_MINUTES, DEFAULT_CHECKIN_OFFSET_MINUTES),
                ): vol.All(int, vol.Range(min=-120, max=240)),
                vol.Optional(
                    CONF_CHECKOUT_OFFSET_MINUTES,
                    default=current.get(CONF_CHECKOUT_OFFSET_MINUTES, DEFAULT_CHECKOUT_OFFSET_MINUTES),
                ): vol.All(int, vol.Range(min=-120, max=240)),
                vol.Optional(
                    CONF_KEYMASTER_SLOT,
                    default=current.get(CONF_KEYMASTER_SLOT, ""),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
