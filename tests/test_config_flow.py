"""Tests for the reconfigure / reauth credential-update flows."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.str_concierge.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    DOMAIN,
)
from custom_components.str_concierge.coordinator import STRCoordinator
from custom_components.str_concierge.providers.base import Property

from .conftest import SAMPLE_PROPERTY

FLOW_PROVIDER = "custom_components.str_concierge.config_flow.create_provider"


def _auth_error(status: int = 401) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=status
    )


def _provider(props=None, exc: Exception | None = None) -> MagicMock:
    p = MagicMock()
    p.get_properties = AsyncMock(
        return_value=props if props is not None else [SAMPLE_PROPERTY],
        side_effect=exc,
    )
    return p


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Let HA's loader find custom_components/str_concierge."""


@pytest.fixture(autouse=True)
def _no_reload():
    """Don't actually set the integration up after the entry is updated."""
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        AsyncMock(return_value=True),
    ):
        yield


async def _start(hass: HomeAssistant, entry, source: str):
    if source == SOURCE_REAUTH:
        return await entry.start_reauth_flow(hass)
    return await entry.start_reconfigure_flow(hass)


@pytest.mark.parametrize(
    ("source", "step_id", "reason"),
    [
        (SOURCE_RECONFIGURE, "reconfigure", "reconfigure_successful"),
        (SOURCE_REAUTH, "reauth_confirm", "reauth_successful"),
    ],
)
async def test_updates_api_key_in_place(
    hass: HomeAssistant, mock_config_entry, source, step_id, reason
):
    mock_config_entry.add_to_hass(hass)
    result = await _start(hass, mock_config_entry, source)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step_id

    with patch(FLOW_PROVIDER, return_value=_provider()) as create:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "new-key"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert mock_config_entry.data[CONF_API_KEY] == "new-key"
    # Everything else untouched — same entry, same property, same options.
    assert mock_config_entry.data["property_id"] == "prop-001"
    assert create.call_args.args[1] == "new-key"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize(
    ("exc", "props", "error"),
    [
        (_auth_error(401), None, "invalid_auth"),
        (_auth_error(403), None, "invalid_auth"),
        (aiohttp.ClientConnectionError(), None, "cannot_connect"),
        (None, [Property(id="other", name="Elsewhere")], "property_not_found"),
    ],
)
async def test_reconfigure_errors_keep_old_key(
    hass: HomeAssistant, mock_config_entry, exc, props, error
):
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    with patch(FLOW_PROVIDER, return_value=_provider(props=props, exc=exc)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "bad-key"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert mock_config_entry.data[CONF_API_KEY] == "test-api-key"


async def test_reconfigure_custom_endpoint_can_change_base_url(
    hass: HomeAssistant, mock_custom_entry
):
    mock_custom_entry.add_to_hass(hass)
    result = await mock_custom_entry.start_reconfigure_flow(hass)
    assert CONF_BASE_URL in result["data_schema"].schema

    with patch(FLOW_PROVIDER, return_value=_provider()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "new-token", CONF_BASE_URL: "https://new.example.com"},
        )

    assert result["reason"] == "reconfigure_successful"
    assert mock_custom_entry.data[CONF_API_KEY] == "new-token"
    assert mock_custom_entry.data[CONF_BASE_URL] == "https://new.example.com"


async def test_reconfigure_host_tools_has_no_base_url_field(
    hass: HomeAssistant, mock_config_entry
):
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert CONF_BASE_URL not in result["data_schema"].schema


async def test_coordinator_raises_auth_failed_on_401(
    hass: HomeAssistant, mock_provider
):
    mock_provider.get_property_data = AsyncMock(side_effect=_auth_error(401))
    coordinator = STRCoordinator(
        hass=hass,
        provider=mock_provider,
        property_id="prop-001",
        property_name="Beach House",
        poll_interval=300,
        entry_id="x",
        arrival_window_minutes=240,
        vacancy_threshold_days=30,
        lock_minutes_before_checkin=0,
        lock_minutes_after_checkout=60,
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
