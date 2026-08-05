"""Light entities for Casambi units, groups and scene controls."""
from __future__ import annotations
from typing import Any
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .api import Esp32CasambiClient
from .const import CASAMBI_MAX_LEVEL, CASAMBI_OFF_LEVEL_THRESHOLD, DOMAIN
from .coordinator import Esp32CasambiCoordinator
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    rt=hass.data[DOMAIN][entry.entry_id]; c=rt["coordinator"]; api=rt["client"]; host=entry.data.get(CONF_HOST,"esp32")
    async_add_entities([*(UnitLight(c,api,host,x) for x in c.data.get("units",[])), *(GroupLight(c,api,host,x) for x in c.data.get("groups",[])), *(SceneLight(c,api,host,x) for x in c.data.get("scenes",[]))])
class Base(CoordinatorEntity[Esp32CasambiCoordinator], LightEntity):
    _attr_has_entity_name=True
    def __init__(self,c,api,host,item,kind): super().__init__(c); self.client=api; self.host=host; self.kind=kind; self.item_id=_id(item); self._attr_unique_id=f"{DOMAIN}_{host}_{kind}_{self.item_id}"; self._attr_name=_name(item,f"Casambi {kind.title()} {self.item_id}")
    @property
    def item(self):
        for x in self.coordinator.data.get(f"{self.kind}s",[]):
            if _id(x)==self.item_id: return x
        return {}
    @property
    def brightness(self):
        # The controller can report level=1 for a fixture that is actually off.
        # Home Assistant would show that as 1%, so normalize the off range to 0.
        if self.is_on is False:
            return 0
        return _byte(self.item.get("level", self.item.get("brightness")))
    @property
    def is_on(self):
        # Do NOT trust the firmware's `on` flag for actual light output.
        # In esp32-casambi it can effectively mean reachable/online rather than
        # "currently glowing". Therefore Home Assistant state is derived from
        # level/brightness first. This fixes lights that are off in Casambi but
        # stayed on in HA with 1% brightness.
        raw_level = _byte(self.item.get("level", self.item.get("brightness")))
        if raw_level is not None:
            return raw_level > CASAMBI_OFF_LEVEL_THRESHOLD
        if isinstance(self.item.get("on"), bool):
            return self.item["on"]
        return None
class UnitLight(Base):
    def __init__(self,c,api,host,item): super().__init__(c,api,host,item,"unit")
    @property
    def supported_color_modes(self): return {ColorMode.BRIGHTNESS}
    @property
    def color_mode(self): return ColorMode.BRIGHTNESS
    async def async_turn_on(self, **kw):
        if ATTR_BRIGHTNESS in kw: await self.client.async_unit_level(self.item_id, kw[ATTR_BRIGHTNESS])
        else: await self.client.async_unit_on(self.item_id)
        if ATTR_COLOR_TEMP_KELVIN in kw: await self.client.async_unit_temperature(self.item_id, kw[ATTR_COLOR_TEMP_KELVIN])
        if ATTR_RGB_COLOR in kw: await self.client.async_unit_color(self.item_id, *kw[ATTR_RGB_COLOR])
        await self.coordinator.async_request_refresh()
    async def async_turn_off(self, **kw): await self.client.async_unit_off(self.item_id); await self.coordinator.async_request_refresh()
class GroupLight(Base):
    _attr_supported_color_modes={ColorMode.BRIGHTNESS}; _attr_color_mode=ColorMode.BRIGHTNESS
    def __init__(self,c,api,host,item): super().__init__(c,api,host,item,"group")
    async def async_turn_on(self, **kw): await self.client.async_group_level(self.item_id, kw.get(ATTR_BRIGHTNESS,self.brightness or CASAMBI_MAX_LEVEL)); await self.coordinator.async_request_refresh()
    async def async_turn_off(self, **kw): await self.client.async_group_level(self.item_id,0); await self.coordinator.async_request_refresh()
class SceneLight(Base):
    _attr_supported_color_modes={ColorMode.BRIGHTNESS}; _attr_color_mode=ColorMode.BRIGHTNESS
    def __init__(self,c,api,host,item): super().__init__(c,api,host,item,"scene"); self._attr_unique_id=f"{DOMAIN}_{host}_scene_light_{self.item_id}"; self._attr_name=f"{self._attr_name} Scene Control"
    async def async_turn_on(self, **kw):
        if ATTR_BRIGHTNESS in kw: await self.client.async_scene_level(self.item_id, kw[ATTR_BRIGHTNESS])
        else: await self.client.async_scene_on(self.item_id)
        await self.coordinator.async_request_refresh()
    async def async_turn_off(self, **kw): await self.client.async_scene_off(self.item_id); await self.coordinator.async_request_refresh()
def _id(item):
    for k in ("id","unitId","groupId","sceneId"):
        try:
            if item.get(k) is not None: return int(item[k])
        except Exception: pass
    return 0
def _name(item,fallback): return next((str(item[k]).strip() for k in ("name","label","address") if item.get(k)), fallback)
def _byte(v):
    if v is None:
        return None
    value = max(0, min(CASAMBI_MAX_LEVEL, int(v)))
    return 0 if value <= CASAMBI_OFF_LEVEL_THRESHOLD else value
