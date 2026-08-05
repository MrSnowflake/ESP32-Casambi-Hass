"""The ESP32 Casambi Controller integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Esp32CasambiClient
from .const import CONF_HOST, CONF_PASSWORD, DOMAIN
from .coordinator import Esp32CasambiCoordinator

PLATFORMS: list[Platform] = [Platform.LIGHT]


@dataclass
class Esp32CasambiData:
    """Runtime data stored on the config entry."""

    client: Esp32CasambiClient
    coordinator: Esp32CasambiCoordinator


type Esp32CasambiConfigEntry = ConfigEntry[Esp32CasambiData]


async def async_setup_entry(
    hass: HomeAssistant, entry: Esp32CasambiConfigEntry
) -> bool:
    """Set up ESP32 Casambi Controller from a config entry."""
    session = async_get_clientsession(hass)
    client = Esp32CasambiClient(
        session, entry.data[CONF_HOST], entry.data.get(CONF_PASSWORD, "")
    )

    coordinator = Esp32CasambiCoordinator(hass, client)
    # Establishes the initial unit list via REST first - this is also
    # what surfaces a bad password as ConfigEntryAuthFailed right away,
    # before the WebSocket (which would hit the same auth check) even
    # gets a chance to connect.
    await coordinator.async_config_entry_first_refresh()

    # WebSocket takes over as the live-update source from here; REST
    # polling automatically resumes if it ever disconnects.
    coordinator.start_websocket()
    entry.async_on_unload(coordinator.async_stop)

    entry.runtime_data = Esp32CasambiData(client=client, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: Esp32CasambiConfigEntry
) -> bool:
    """Unload a config entry.

    The WebSocket task is stopped automatically via the
    entry.async_on_unload(coordinator.async_stop) hook registered above.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
