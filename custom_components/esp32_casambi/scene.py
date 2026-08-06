"""Native HA scene entities for Casambi scenes."""
from __future__ import annotations
from typing import Any
from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddEntitiesCallback)->None:
    rt=hass.data[DOMAIN][entry.entry_id]; c=rt["coordinator"]; api=rt["client"]; host=entry.data.get(CONF_HOST,"esp32")
    async_add_entities(SceneEntity(c,api,host,x) for x in c.data.get("scenes",[]))
class SceneEntity(CoordinatorEntity, Scene):
    _attr_has_entity_name=True
    def __init__(self,c,api,host,item): super().__init__(c); self.client=api; self.scene_id=_id(item); self._attr_unique_id=f"{DOMAIN}_{host}_scene_{self.scene_id}"; self._attr_name=_name(item,f"Casambi Scene {self.scene_id}")
    async def async_activate(self,**kwargs:Any)->None: await self.client.async_scene_on(self.scene_id); await self.coordinator.async_request_refresh()
def _id(item):
    try: return int(item.get("id",item.get("sceneId",0)))
    except Exception: return 0
def _name(item,fallback): return str(item.get("name") or item.get("label") or fallback).strip()
