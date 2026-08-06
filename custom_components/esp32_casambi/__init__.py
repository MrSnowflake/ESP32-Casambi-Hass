"""ESP32 Casambi integration."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import Esp32CasambiClient
from .const import CONF_HOST, CONF_PASSWORD, DOMAIN, PLATFORMS
from .coordinator import Esp32CasambiCoordinator
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry)->bool:
    client=Esp32CasambiClient(async_get_clientsession(hass),entry.data[CONF_HOST],entry.data.get(CONF_PASSWORD)); coordinator=Esp32CasambiCoordinator(hass,client)
    await coordinator.async_config_entry_first_refresh(); coordinator.async_start_websocket(); hass.data.setdefault(DOMAIN,{})[entry.entry_id]={"client":client,"coordinator":coordinator}
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS); return True
async def async_unload_entry(hass:HomeAssistant,entry:ConfigEntry)->bool:
    runtime=hass.data.get(DOMAIN,{}).get(entry.entry_id)
    if runtime: await runtime["coordinator"].async_stop_websocket()
    ok=await hass.config_entries.async_unload_platforms(entry,PLATFORMS)
    if ok: hass.data[DOMAIN].pop(entry.entry_id,None)
    return ok
