"""Light platform for the ESP32 Casambi Controller integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import Esp32CasambiConfigEntry
from .api import Esp32CasambiApiError
from .const import DOMAIN
from .coordinator import Esp32CasambiCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Esp32CasambiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lights for each known Casambi unit."""
    data = entry.runtime_data
    coordinator = data.coordinator

    known_unit_ids: set[int] = set()

    @callback
    def _async_add_new_units() -> None:
        """Add entities for any unit not seen before (e.g. added later
        in the Casambi app and picked up on the next coordinator poll)."""
        new_entities = []
        for unit in coordinator.data.get("units", []):
            unit_id = unit["id"]
            if unit_id in known_unit_ids:
                continue
            known_unit_ids.add(unit_id)
            new_entities.append(
                Esp32CasambiLight(coordinator, data.client, entry.entry_id, unit)
            )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_units()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_units))


class Esp32CasambiLight(CoordinatorEntity[Esp32CasambiCoordinator], LightEntity):
    """Representation of a single Casambi light unit.

    As of the akumap fork, GET /api/units reports real-time `on`, `level`,
    and (for CCT-capable fixtures) `colorTemp` values - these are pushed
    into the controller's in-memory state from BLE status broadcasts, so
    they reflect changes made via the official Casambi app, timers,
    sensors, or other controllers, not just commands sent from HA. This
    entity reads state straight from the coordinator; no local/optimistic
    tracking is needed anymore. Vertical light distribution and RGB color
    are not exposed here (Home Assistant's light entity model doesn't map
    cleanly onto "vertical"), only on/off, brightness, and color
    temperature.
    """

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: Esp32CasambiCoordinator,
        client,
        entry_id: str,
        unit: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._unit_id: int = unit["id"]

        self._attr_unique_id = f"{entry_id}_unit_{self._unit_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": unit.get("name", f"Unit {self._unit_id}"),
            "manufacturer": "Casambi",
            "via_device": (DOMAIN, entry_id),
        }

        # CCT capability is fixed for a given physical fixture, so it's
        # safe to decide the supported color modes once at creation time
        # from whichever unit snapshot triggered entity creation.
        if "cctMin" in unit and "cctMax" in unit:
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_min_color_temp_kelvin = unit["cctMin"]
            self._attr_max_color_temp_kelvin = unit["cctMax"]
        else:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS

    @property
    def _current_unit(self) -> dict[str, Any] | None:
        for unit in self.coordinator.data.get("units", []):
            if unit["id"] == self._unit_id:
                return unit
        return None

    @property
    def name(self) -> str:
        unit = self._current_unit
        return unit.get("name", f"Unit {self._unit_id}") if unit else f"Unit {self._unit_id}"

    @property
    def available(self) -> bool:
        """Entity is available if the coordinator is working and the unit
        is reported online by the controller."""
        if not super().available:
            return False
        unit = self._current_unit
        if unit is None:
            # Unit disappeared from the controller's list entirely.
            return False
        return unit.get("online", True)

    @property
    def is_on(self) -> bool | None:
        unit = self._current_unit
        if unit is None:
            return None
        return bool(unit.get("on", False))

    @property
    def brightness(self) -> int | None:
        unit = self._current_unit
        if unit is None:
            return None
        return unit.get("level")

    @property
    def color_temp_kelvin(self) -> int | None:
        """Convert the controller's normalized 0-255 colorTemp to Kelvin.

        Formula matches the upstream README: kelvin = cctMin +
        (colorTemp / 255) * (cctMax - cctMin).
        """
        unit = self._current_unit
        if unit is None or "colorTemp" not in unit:
            return None
        cct_min = unit.get("cctMin", self._attr_min_color_temp_kelvin)
        cct_max = unit.get("cctMax", self._attr_max_color_temp_kelvin)
        return round(cct_min + (unit["colorTemp"] / 255) * (cct_max - cct_min))

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)

        try:
            # Casambi units accept these as independent operations; send
            # color temp first so a simultaneous brightness+CCT call from
            # HA (e.g. a script) still ends up with both applied.
            if color_temp_kelvin is not None:
                await self._client.async_unit_temperature(
                    self._unit_id, color_temp_kelvin
                )
            if brightness is not None:
                await self._client.async_unit_level(self._unit_id, brightness)
            elif color_temp_kelvin is None:
                await self._client.async_unit_on(self._unit_id)
        except Esp32CasambiApiError as err:
            _LOGGER.error("Failed to turn on unit %s: %s", self._unit_id, err)
            return

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._client.async_unit_off(self._unit_id)
        except Esp32CasambiApiError as err:
            _LOGGER.error("Failed to turn off unit %s: %s", self._unit_id, err)
            return

        await self.coordinator.async_request_refresh()
