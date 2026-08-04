"""Config flow for the ESP32 Casambi Controller integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Esp32CasambiApiError, Esp32CasambiAuthError, Esp32CasambiClient
from .const import CONF_HOST, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        # Optional: leave empty if the controller has no Casambi password
        # set (open API, pre-auth-firmware compatible).
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)


async def _async_validate_host(hass: HomeAssistant, host: str, password: str) -> str:
    """Try to reach the controller and return its network name (if any)."""
    session = async_get_clientsession(hass)
    client = Esp32CasambiClient(session, host, password)
    status = await client.async_get_status()
    return status.get("network_name") or host


class Esp32CasambiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ESP32 Casambi Controller."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            try:
                network_name = await _async_validate_host(self.hass, host, password)
            except Esp32CasambiAuthError:
                errors["base"] = "invalid_auth"
            except Esp32CasambiApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Casambi ({network_name})",
                    data={CONF_HOST: host, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "example": "192.168.1.100"
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Triggered by ConfigEntryAuthFailed when the stored password no
        longer matches the controller (e.g. changed there, or auth was
        newly enabled after this entry was first set up)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            host = reauth_entry.data[CONF_HOST]

            try:
                await _async_validate_host(self.hass, host, password)
            except Esp32CasambiAuthError:
                errors["base"] = "invalid_auth"
            except Esp32CasambiApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD, default=""): str}),
            errors=errors,
        )
