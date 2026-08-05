"""Data coordinator for ESP32 Casambi."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Esp32CasambiApiError, Esp32CasambiAuthError, Esp32CasambiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class Esp32CasambiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch units, groups and scenes from the controller."""

    def __init__(self, hass: HomeAssistant, client: Esp32CasambiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            units = await self.client.async_get_units()
            groups = await self.client.async_get_groups()
            scenes = await self.client.async_get_scenes()
        except Esp32CasambiAuthError as err:
            raise UpdateFailed("ESP32 Casambi authentication failed") from err
        except Esp32CasambiApiError as err:
            _LOGGER.debug("Could not refresh ESP32 Casambi data: %s", err)
            if self.data is not None:
                return self.data
            raise UpdateFailed(str(err)) from err
        return {"units": units, "groups": groups, "scenes": scenes}
