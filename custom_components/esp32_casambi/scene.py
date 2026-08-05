"""Scene entities for ESP32 Casambi scenes."""
from __future__ import annotations

from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Esp32CasambiClient
from .const import DOMAIN
from .coordinator import Esp32CasambiCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Casambi scenes."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: Esp32CasambiCoordinator = runtime["coordinator"]
    client: Esp32CasambiClient = runtime["client"]
    host = entry.data.get(CONF_HOST, "esp32")
    async_add_entities(
        Esp32CasambiSceneEntity(coordinator, client, host, item)
        for item in coordinator.data.get("scenes", [])
    )


class Esp32CasambiSceneEntity(CoordinatorEntity[Esp32CasambiCoordinator], Scene):
    """Native Home Assistant scene which turns a Casambi scene on."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Esp32CasambiCoordinator, client: Esp32CasambiClient, host: str, item: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.client = client
        self.host = host
        self.scene_id = _item_id(item)
        self._name = _item_name(item, f"Casambi Scene {self.scene_id}")
        self._attr_unique_id = f"{DOMAIN}_{host}_scene_{self.scene_id}"
        self._attr_name = self._name

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, f"{self.host}_scene_{self.scene_id}")},
            "name": self._name,
            "manufacturer": "Casambi via ESP32",
            "model": "Casambi Scene",
            "via_device": (DOMAIN, self.host),
        }

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the Casambi scene."""
        await self.client.async_scene_on(self.scene_id)
        await self.coordinator.async_request_refresh()


def _item_id(item: dict[str, Any]) -> int:
    for key in ("id", "sceneId"):
        try:
            if item.get(key) is not None:
                return int(item[key])
        except (TypeError, ValueError):
            pass
    return 0


def _item_name(item: dict[str, Any], fallback: str) -> str:
    for key in ("name", "label"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback
