"""Async client for the ESP32 Casambi Controller REST API."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp

from .const import API_KEY_HEADER, API_TOKEN_PREFIX, CASAMBI_MAX_LEVEL, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)


def derive_api_key(password: str) -> str:
    """Derive the X-API-Key value from the Casambi network password."""
    digest = hashlib.sha256((API_TOKEN_PREFIX + password).encode("utf-8"))
    return digest.hexdigest()


class Esp32CasambiApiError(Exception):
    """Raised when a call to the ESP32 Casambi Controller fails."""


class Esp32CasambiAuthError(Esp32CasambiApiError):
    """Raised when the controller rejects the configured API key."""


class Esp32CasambiClient:
    """Small REST client for akumap/esp32-casambi."""

    def __init__(self, session: aiohttp.ClientSession, host: str, password: str | None = None) -> None:
        self.session = session
        self.host = host.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
        self.password = password or ""
        self.api_key = derive_api_key(self.password) if self.password else None

    @property
    def base_url(self) -> str:
        """Return the controller base URL."""
        if ":" in self.host:
            return f"http://{self.host}"
        return f"http://{self.host}:{DEFAULT_PORT}"

    @property
    def headers(self) -> dict[str, str]:
        """Return default request headers."""
        if self.api_key:
            return {API_KEY_HEADER: self.api_key}
        return {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Call the controller and decode JSON when present."""
        url = f"{self.base_url}{path}"
        headers = dict(self.headers)
        if json is not None:
            headers["Content-Type"] = "application/json"

        try:
            async with self.session.request(method, url, headers=headers, json=json, timeout=10) as resp:
                if resp.status in (401, 403):
                    raise Esp32CasambiAuthError("ESP32 Casambi authentication failed")
                if resp.status >= 400:
                    body = await resp.text()
                    raise Esp32CasambiApiError(f"{method} {path} failed with HTTP {resp.status}: {body}")
                if resp.content_type == "application/json":
                    return await resp.json()
                text = await resp.text()
                return text or None
        except Esp32CasambiApiError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise Esp32CasambiApiError(f"Could not call ESP32 Casambi API {method} {path}: {err}") from err

    async def async_get_units(self) -> list[dict[str, Any]]:
        """Return all Casambi units."""
        data = await self._request("GET", "/api/units")
        return _as_list(data, "units")

    async def async_get_groups(self) -> list[dict[str, Any]]:
        """Return all Casambi groups."""
        data = await self._request("GET", "/api/groups")
        return _as_list(data, "groups")

    async def async_get_scenes(self) -> list[dict[str, Any]]:
        """Return all Casambi scenes."""
        data = await self._request("GET", "/api/scenes")
        return _as_list(data, "scenes")

    async def async_unit_on(self, unit_id: int) -> None:
        await self._request("POST", f"/api/units/{unit_id}/on")

    async def async_unit_off(self, unit_id: int) -> None:
        await self._request("POST", f"/api/units/{unit_id}/off")

    async def async_unit_level(self, unit_id: int, level: int) -> None:
        await self._request("POST", f"/api/units/{unit_id}/level", json={"level": _clamp_byte(level)})

    async def async_unit_temperature(self, unit_id: int, kelvin: int) -> None:
        await self._request("POST", f"/api/units/{unit_id}/temperature", json={"kelvin": int(kelvin)})

    async def async_unit_color(self, unit_id: int, red: int, green: int, blue: int) -> None:
        await self._request(
            "POST",
            f"/api/units/{unit_id}/color",
            json={"r": _clamp_byte(red), "g": _clamp_byte(green), "b": _clamp_byte(blue)},
        )

    async def async_unit_vertical(self, unit_id: int, value: int) -> None:
        await self._request("POST", f"/api/units/{unit_id}/vertical", json={"value": _clamp_byte(value)})

    async def async_unit_slider(self, unit_id: int, value: int) -> None:
        await self._request("POST", f"/api/units/{unit_id}/slider", json={"value": _clamp_byte(value)})

    async def async_unit_state(self, unit_id: int, state: dict[str, int]) -> None:
        await self._request("POST", f"/api/units/{unit_id}/state", json={k: _clamp_byte(v) for k, v in state.items()})

    async def async_group_level(self, group_id: int, level: int) -> None:
        await self._request("POST", f"/api/groups/{group_id}/level", json={"level": _clamp_byte(level)})

    async def async_group_vertical(self, group_id: int, value: int) -> None:
        await self._request("POST", f"/api/groups/{group_id}/vertical", json={"value": _clamp_byte(value)})

    async def async_group_slider(self, group_id: int, value: int) -> None:
        await self._request("POST", f"/api/groups/{group_id}/slider", json={"value": _clamp_byte(value)})

    async def async_scene_on(self, scene_id: int) -> None:
        await self._request("POST", f"/api/scenes/{scene_id}/on")

    async def async_scene_off(self, scene_id: int) -> None:
        await self._request("POST", f"/api/scenes/{scene_id}/off")

    async def async_scene_level(self, scene_id: int, level: int) -> None:
        await self._request("POST", f"/api/scenes/{scene_id}/level", json={"level": _clamp_byte(level)})


def _as_list(data: Any, key: str) -> list[dict[str, Any]]:
    """Normalize common API list shapes."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _clamp_byte(value: int) -> int:
    return max(0, min(CASAMBI_MAX_LEVEL, int(value)))
