"""Config flow for ESP32 Casambi."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import Esp32CasambiApiError, Esp32CasambiAuthError, Esp32CasambiClient
from .const import DOMAIN


class Esp32CasambiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ESP32 Casambi."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            session = async_create_clientsession(self.hass)
            client = Esp32CasambiClient(session, user_input[CONF_HOST], user_input.get(CONF_PASSWORD))
            try:
                await client.async_get_units()
            except Esp32CasambiAuthError:
                errors["base"] = "invalid_auth"
            except Esp32CasambiApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)
        schema = vol.Schema({vol.Required(CONF_HOST): str, vol.Optional(CONF_PASSWORD, default=""): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
