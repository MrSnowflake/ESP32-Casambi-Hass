"""Async REST and WebSocket client for ESP32 Casambi."""
from __future__ import annotations
import hashlib
from typing import Any
import aiohttp
from .const import API_KEY_HEADER, API_TOKEN_PREFIX, CASAMBI_MAX_LEVEL, DEFAULT_PORT

def derive_api_key(password: str) -> str:
    return hashlib.sha256((API_TOKEN_PREFIX + password).encode()).hexdigest()

class Esp32CasambiApiError(Exception): pass
class Esp32CasambiAuthError(Esp32CasambiApiError): pass

class Esp32CasambiClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, password: str | None = None) -> None:
        self.session = session
        self.host = host.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
        self.password = password or ""
        self.api_key = derive_api_key(self.password) if self.password else None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}" if ":" in self.host else f"http://{self.host}:{DEFAULT_PORT}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}/ws" if ":" in self.host else f"ws://{self.host}:{DEFAULT_PORT}/ws"

    @property
    def headers(self) -> dict[str, str]:
        return {API_KEY_HEADER: self.api_key} if self.api_key else {}

    async def async_ws_connect(self) -> aiohttp.ClientWebSocketResponse:
        return await self.session.ws_connect(self.ws_url, headers=self.headers, heartbeat=30, timeout=10)

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> Any:
        headers = dict(self.headers)
        if json is not None:
            headers["Content-Type"] = "application/json"
        try:
            async with self.session.request(method, f"{self.base_url}{path}", headers=headers, json=json, timeout=10) as resp:
                if resp.status in (401, 403):
                    raise Esp32CasambiAuthError("ESP32 Casambi authentication failed")
                if resp.status >= 400:
                    raise Esp32CasambiApiError(f"{method} {path} failed with HTTP {resp.status}: {await resp.text()}")
                return await resp.json() if resp.content_type == "application/json" else (await resp.text() or None)
        except Esp32CasambiApiError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise Esp32CasambiApiError(str(err)) from err

    async def async_get_units(self): return _as_list(await self._request("GET", "/api/units"), "units")
    async def async_get_groups(self): return _as_list(await self._request("GET", "/api/groups"), "groups")
    async def async_get_scenes(self): return _as_list(await self._request("GET", "/api/scenes"), "scenes")
    async def async_unit_on(self, i:int): await self._request("POST", f"/api/units/{i}/on")
    async def async_unit_off(self, i:int): await self._request("POST", f"/api/units/{i}/off")
    async def async_unit_level(self, i:int, level:int): await self._request("POST", f"/api/units/{i}/level", json={"level": _b(level)})
    async def async_unit_temperature(self, i:int, kelvin:int): await self._request("POST", f"/api/units/{i}/temperature", json={"kelvin": int(kelvin)})
    async def async_unit_color(self, i:int, r:int, g:int, b:int): await self._request("POST", f"/api/units/{i}/color", json={"r": _b(r), "g": _b(g), "b": _b(b)})
    async def async_unit_vertical(self, i:int, value:int): await self._request("POST", f"/api/units/{i}/vertical", json={"value": _b(value)})
    async def async_unit_slider(self, i:int, value:int): await self._request("POST", f"/api/units/{i}/slider", json={"value": _b(value)})
    async def async_unit_state(self, i:int, state:dict[str,int]): await self._request("POST", f"/api/units/{i}/state", json={k:_b(v) for k,v in state.items()})
    async def async_group_level(self, i:int, level:int): await self._request("POST", f"/api/groups/{i}/level", json={"level": _b(level)})
    async def async_group_vertical(self, i:int, value:int): await self._request("POST", f"/api/groups/{i}/vertical", json={"value": _b(value)})
    async def async_group_slider(self, i:int, value:int): await self._request("POST", f"/api/groups/{i}/slider", json={"value": _b(value)})
    async def async_scene_on(self, i:int): await self._request("POST", f"/api/scenes/{i}/on")
    async def async_scene_off(self, i:int): await self._request("POST", f"/api/scenes/{i}/off")
    async def async_scene_level(self, i:int, level:int): await self._request("POST", f"/api/scenes/{i}/level", json={"level": _b(level)})

def _as_list(data: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(data, list): return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get(key), list): return [x for x in data[key] if isinstance(x, dict)]
    return []
def _b(v: Any) -> int: return max(0, min(CASAMBI_MAX_LEVEL, int(v)))
