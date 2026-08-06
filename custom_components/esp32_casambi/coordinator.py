"""Coordinator with polling fallback, WebSocket live updates and local optimistic merges."""
from __future__ import annotations
import asyncio
import contextlib
import json
import logging
from copy import deepcopy
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import Esp32CasambiApiError, Esp32CasambiAuthError, Esp32CasambiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
_LOGGER = logging.getLogger(__name__)

class Esp32CasambiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator using REST for discovery/fallback and /ws for live state."""
    def __init__(self, hass: HomeAssistant, client: Esp32CasambiClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL))
        self.client = client
        self._ws_task: asyncio.Task[None] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return {
                "units": await self.client.async_get_units(),
                "groups": await self.client.async_get_groups(),
                "scenes": await self.client.async_get_scenes(),
            }
        except Esp32CasambiAuthError as err:
            raise UpdateFailed("ESP32 Casambi authentication failed") from err
        except Esp32CasambiApiError as err:
            if self.data is not None:
                return self.data
            raise UpdateFailed(str(err)) from err

    def async_start_websocket(self) -> None:
        if self._ws_task is None or self._ws_task.done():
            self._ws_task = self.hass.loop.create_task(self._ws_loop())

    async def async_stop_websocket(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None

    def async_merge_local_update(self, collection: str, item_id: int, values: dict[str, Any]) -> None:
        """Apply a command result immediately without forcing a blocking REST refresh.

        WebSocket and the periodic poll will still reconcile the real controller state.
        """
        data = deepcopy(self.data or {"units": [], "groups": [], "scenes": []})
        update = {"id": item_id, **values}
        if _merge(data, collection, update):
            self.async_set_updated_data(data)

    async def _ws_loop(self) -> None:
        delay = 2
        while True:
            try:
                async with await self.client.async_ws_connect() as ws:
                    _LOGGER.debug("ESP32 Casambi WebSocket connected")
                    delay = 2
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self._handle_ws_text(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            self._handle_ws_text(msg.data.decode("utf-8", "ignore"))
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("ESP32 Casambi WebSocket reconnect needed: %s", err)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    def _handle_ws_text(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            _LOGGER.debug("Ignoring non-JSON WebSocket payload: %s", text)
            return
        data = deepcopy(self.data or {"units": [], "groups": [], "scenes": []})
        changed = False
        for item in (payload if isinstance(payload, list) else [payload]):
            changed = _merge_item(data, item) or changed
        if changed:
            self.async_set_updated_data(data)

def _merge_item(data: dict[str, Any], item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    changed = False
    for coll in ("units", "groups", "scenes"):
        if isinstance(item.get(coll), list):
            for entry in item[coll]:
                changed = _merge(data, coll, entry) or changed
    for key, coll in (("unit", "units"), ("group", "groups"), ("scene", "scenes")):
        if isinstance(item.get(key), dict):
            changed = _merge(data, coll, item[key]) or changed
    typ = str(item.get("type") or item.get("event") or item.get("kind") or "").lower()
    if typ in ("unit", "unit_state", "unitstate", "status", "state"):
        changed = _merge(data, "units", item) or changed
    elif typ in ("group", "group_state", "groupstate"):
        changed = _merge(data, "groups", item) or changed
    elif typ in ("scene", "scene_state", "scenestate"):
        changed = _merge(data, "scenes", item) or changed
    elif _looks_unit_state(item):
        changed = _merge(data, "units", item) or changed
    return changed

def _looks_unit_state(item: dict[str, Any]) -> bool:
    return any(k in item for k in ("id", "unitId")) and any(k in item for k in ("on", "level", "brightness", "colorTemp", "kelvin", "temperature", "r", "g", "b", "rgb", "color", "vertical", "slider"))

def _merge(data: dict[str, Any], coll: str, update: Any) -> bool:
    if not isinstance(update, dict):
        return False
    ident = _id(update)
    if ident is None:
        return False
    items = data.setdefault(coll, [])
    if not isinstance(items, list):
        data[coll] = items = []
    for n, old in enumerate(items):
        if isinstance(old, dict) and _id(old) == ident:
            new = {**old, **update}
            if new != old:
                items[n] = new
                return True
            return False
    items.append(update)
    return True

def _id(item: dict[str, Any]) -> int | None:
    for key in ("id", "unitId", "groupId", "sceneId"):
        try:
            if item.get(key) is not None:
                return int(item[key])
        except (TypeError, ValueError):
            return None
    return None
