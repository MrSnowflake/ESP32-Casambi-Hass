"""DataUpdateCoordinator for the ESP32 Casambi Controller.

Polls GET /api/units, which (as of the akumap fork) returns real-time
on/level/vertical/colorTemp state pushed from BLE status broadcasts, not
just static discovery data - so this also drives live entity state, not
only "does this unit exist" discovery.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import Esp32CasambiApiError, Esp32CasambiAuthError, Esp32CasambiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class Esp32CasambiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches live unit state from the controller."""

    def __init__(
        self, hass: HomeAssistant, client: Esp32CasambiClient
    ) -> None:
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
        except Esp32CasambiAuthError as err:
            # Password was changed on the controller (or auth was newly
            # enabled) since this entry was set up - prompt the user to
            # re-enter it instead of silently polling a 401 forever.
            raise ConfigEntryAuthFailed(str(err)) from err
        except Esp32CasambiApiError as err:
            _LOGGER.debug("Could not refresh unit list: %s", err)
            # Keep previously known units instead of marking everything
            # unavailable just because one poll failed.
            return self.data or {"units": []}

        return {"units": units}
