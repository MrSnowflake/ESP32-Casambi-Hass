"""Light entities for ESP32 Casambi units, groups and scenes."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Esp32CasambiClient
from .const import CASAMBI_MAX_LEVEL, DOMAIN
from .coordinator import Esp32CasambiCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up light entities."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: Esp32CasambiCoordinator = runtime["coordinator"]
    client: Esp32CasambiClient = runtime["client"]
    host = entry.data.get(CONF_HOST, "esp32")

    platform = async_get_current_platform()
    platform.async_register_entity_service(
        "set_vertical",
        {vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=CASAMBI_MAX_LEVEL))},
        "async_set_vertical",
    )
    platform.async_register_entity_service(
        "set_slider",
        {vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=CASAMBI_MAX_LEVEL))},
        "async_set_slider",
    )
    platform.async_register_entity_service(
        "set_unit_state",
        {vol.Required("state"): cv.schema_with_slug_keys(vol.All(vol.Coerce(int), vol.Range(min=0, max=CASAMBI_MAX_LEVEL)))},
        "async_set_unit_state",
    )

    entities: list[LightEntity] = []
    entities.extend(Esp32CasambiUnitLight(coordinator, client, host, item) for item in coordinator.data.get("units", []))
    entities.extend(Esp32CasambiGroupLight(coordinator, client, host, item) for item in coordinator.data.get("groups", []))
    entities.extend(Esp32CasambiSceneLight(coordinator, client, host, item) for item in coordinator.data.get("scenes", []))
    async_add_entities(entities)


class Esp32CasambiBaseLight(CoordinatorEntity[Esp32CasambiCoordinator], LightEntity):
    """Shared base for Casambi light-like entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Esp32CasambiCoordinator,
        client: Esp32CasambiClient,
        host: str,
        item: dict[str, Any],
        kind: str,
    ) -> None:
        super().__init__(coordinator)
        self.client = client
        self.host = host
        self.kind = kind
        self.item_id = _item_id(item)
        self._initial_name = _item_name(item, f"Casambi {kind.title()} {self.item_id}")
        self._attr_unique_id = f"{DOMAIN}_{host}_{kind}_{self.item_id}"
        self._attr_name = self._initial_name

    @property
    def item(self) -> dict[str, Any]:
        """Return the latest item data from the coordinator."""
        for candidate in self.coordinator.data.get(f"{self.kind}s", []):
            if _item_id(candidate) == self.item_id:
                return candidate
        return {}

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, f"{self.host}_{self.kind}_{self.item_id}")},
            "name": self._initial_name,
            "manufacturer": "Casambi via ESP32",
            "model": f"Casambi {self.kind.title()}",
            "via_device": (DOMAIN, self.host),
        }

    @property
    def brightness(self) -> int | None:
        level = self.item.get("level")
        if level is None:
            level = self.item.get("brightness")
        return _byte_or_none(level)

    @property
    def is_on(self) -> bool | None:
        state = self.item.get("on")
        if isinstance(state, bool):
            return state
        level = self.brightness
        if level is not None:
            return level > 0
        return None


class Esp32CasambiUnitLight(Esp32CasambiBaseLight):
    """Individual Casambi unit."""

    def __init__(self, coordinator: Esp32CasambiCoordinator, client: Esp32CasambiClient, host: str, item: dict[str, Any]) -> None:
        super().__init__(coordinator, client, host, item, "unit")

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        modes = {ColorMode.BRIGHTNESS}
        if self._supports_color_temp:
            modes.add(ColorMode.COLOR_TEMP)
        if self._supports_rgb:
            modes.add(ColorMode.RGB)
        return modes

    @property
    def color_mode(self) -> ColorMode:
        if self._supports_rgb and self.rgb_color:
            return ColorMode.RGB
        if self._supports_color_temp and self.color_temp_kelvin:
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def _supports_color_temp(self) -> bool:
        item = self.item
        return item.get("cctMin") is not None and item.get("cctMax") is not None

    @property
    def _supports_rgb(self) -> bool:
        item = self.item
        return any(key in item for key in ("r", "red", "rgb", "color"))

    @property
    def min_color_temp_kelvin(self) -> int | None:
        return _int_or_none(self.item.get("cctMin"))

    @property
    def max_color_temp_kelvin(self) -> int | None:
        return _int_or_none(self.item.get("cctMax"))

    @property
    def color_temp_kelvin(self) -> int | None:
        for key in ("colorTemp", "kelvin", "temperature"):
            value = _int_or_none(self.item.get(key))
            if value is not None:
                return value
        return None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        item = self.item
        if isinstance(item.get("rgb"), list | tuple) and len(item["rgb"]) >= 3:
            return tuple(_clamp_byte(v) for v in item["rgb"][:3])  # type: ignore[return-value]
        if isinstance(item.get("color"), dict):
            color = item["color"]
            return (_clamp_byte(color.get("r", 0)), _clamp_byte(color.get("g", 0)), _clamp_byte(color.get("b", 0)))
        if any(k in item for k in ("r", "red")):
            return (_clamp_byte(item.get("r", item.get("red", 0))), _clamp_byte(item.get("g", item.get("green", 0))), _clamp_byte(item.get("b", item.get("blue", 0))))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            await self.client.async_unit_level(self.item_id, kwargs[ATTR_BRIGHTNESS])
        elif kwargs.get(ATTR_COLOR_TEMP_KELVIN) is None and kwargs.get(ATTR_RGB_COLOR) is None:
            await self.client.async_unit_on(self.item_id)

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            await self.client.async_unit_temperature(self.item_id, kwargs[ATTR_COLOR_TEMP_KELVIN])
        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs[ATTR_RGB_COLOR]
            await self.client.async_unit_color(self.item_id, red, green, blue)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.client.async_unit_off(self.item_id)
        await self.coordinator.async_request_refresh()

    async def async_set_vertical(self, value: int) -> None:
        await self.client.async_unit_vertical(self.item_id, value)
        await self.coordinator.async_request_refresh()

    async def async_set_slider(self, value: int) -> None:
        await self.client.async_unit_slider(self.item_id, value)
        await self.coordinator.async_request_refresh()

    async def async_set_unit_state(self, state: dict[str, int]) -> None:
        await self.client.async_unit_state(self.item_id, state)
        await self.coordinator.async_request_refresh()


class Esp32CasambiGroupLight(Esp32CasambiBaseLight):
    """Casambi group exposed as a dimmable light."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: Esp32CasambiCoordinator, client: Esp32CasambiClient, host: str, item: dict[str, Any]) -> None:
        super().__init__(coordinator, client, host, item, "group")

    async def async_turn_on(self, **kwargs: Any) -> None:
        level = kwargs.get(ATTR_BRIGHTNESS, self.brightness or CASAMBI_MAX_LEVEL)
        await self.client.async_group_level(self.item_id, level)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        # The ESP32 API currently documents group level/vertical/slider, but no group /off endpoint.
        await self.client.async_group_level(self.item_id, 0)
        await self.coordinator.async_request_refresh()

    async def async_set_vertical(self, value: int) -> None:
        await self.client.async_group_vertical(self.item_id, value)
        await self.coordinator.async_request_refresh()

    async def async_set_slider(self, value: int) -> None:
        await self.client.async_group_slider(self.item_id, value)
        await self.coordinator.async_request_refresh()


class Esp32CasambiSceneLight(Esp32CasambiBaseLight):
    """Casambi scene exposed as a light-like entity for on/off/level control."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: Esp32CasambiCoordinator, client: Esp32CasambiClient, host: str, item: dict[str, Any]) -> None:
        super().__init__(coordinator, client, host, item, "scene")
        self._attr_unique_id = f"{DOMAIN}_{host}_scene_light_{self.item_id}"
        self._attr_name = f"{self._initial_name} Scene Control"

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            await self.client.async_scene_level(self.item_id, kwargs[ATTR_BRIGHTNESS])
        else:
            await self.client.async_scene_on(self.item_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.client.async_scene_off(self.item_id)
        await self.coordinator.async_request_refresh()


def _item_id(item: dict[str, Any]) -> int:
    for key in ("id", "unitId", "groupId", "sceneId"):
        value = _int_or_none(item.get(key))
        if value is not None:
            return value
    return 0


def _item_name(item: dict[str, Any], fallback: str) -> str:
    for key in ("name", "label", "address"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _byte_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return _clamp_byte(value)


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp_byte(value: Any) -> int:
    return max(0, min(CASAMBI_MAX_LEVEL, int(value)))
