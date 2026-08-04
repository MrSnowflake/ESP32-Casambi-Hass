"""Minimal async client for the ESP32 Casambi Controller REST API."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import aiohttp

from .const import API_TOKEN_PREFIX

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8
API_KEY_HEADER = "X-API-Key"


def derive_api_token(password: str) -> str:
    """Derive the X-API-Key value from the Casambi network password.

    Must mirror the firmware's derivation exactly (see config.h /
    API_TOKEN_PREFIX): hex(SHA-256(API_TOKEN_PREFIX + password)).
    """
    digest = hashlib.sha256((API_TOKEN_PREFIX + password).encode("utf-8"))
    return digest.hexdigest()


class Esp32CasambiApiError(Exception):
    """Raised when a call to the ESP32 Casambi Controller fails."""


class Esp32CasambiAuthError(Esp32CasambiApiError):
    """Raised when the controller rejects the configured API key."""


class Esp32CasambiClient:
    """Thin wrapper around the controller's HTTP REST API.

    See https://github.com/lian/esp32-casambi for the full endpoint list.
    """

    def __init__(
        self, session: aiohttp.ClientSession, host: str, password: str = ""
    ) -> None:
        self._session = session
        self._base_url = f"http://{host}/api"
        # Empty password -> no header sent -> matches the firmware's "empty
        # password = open API" fallback for pre-auth configs.
        self._headers = (
            {API_KEY_HEADER: derive_api_token(password)} if password else {}
        )

    async def async_get_info(self) -> dict[str, Any]:
        """GET /api/info - the only endpoint that stays unauthenticated.

        Useful as a cheap reachability probe before/independent of auth.
        """
        return await self._request("GET", "/info")

    async def async_get_status(self) -> dict[str, Any]:
        """GET /api/status - used during config flow validation.

        Requires auth once the controller has a stored Casambi password, so
        a successful call here also confirms the configured password/token
        is correct.
        """
        return await self._request("GET", "/status")

    async def async_get_units(self) -> list[dict[str, Any]]:
        """GET /api/units - list all light units."""
        data = await self._request("GET", "/units")
        return data.get("units", [])

    async def async_get_groups(self) -> list[dict[str, Any]]:
        """GET /api/groups - list all groups."""
        data = await self._request("GET", "/groups")
        return data.get("groups", [])

    async def async_get_scenes(self) -> list[dict[str, Any]]:
        """GET /api/scenes - list all scenes."""
        data = await self._request("GET", "/scenes")
        return data.get("scenes", [])

    async def async_unit_on(self, unit_id: int) -> None:
        await self._request("POST", f"/units/{unit_id}/on")

    async def async_unit_off(self, unit_id: int) -> None:
        await self._request("POST", f"/units/{unit_id}/off")

    async def async_unit_level(self, unit_id: int, level: int) -> None:
        await self._request(
            "POST", f"/units/{unit_id}/level", json={"level": level}
        )

    async def async_unit_temperature(self, unit_id: int, kelvin: int) -> None:
        await self._request(
            "POST", f"/units/{unit_id}/temperature", json={"kelvin": kelvin}
        )

    async def async_group_level(self, group_id: int, level: int) -> None:
        await self._request(
            "POST", f"/groups/{group_id}/level", json={"level": level}
        )

    async def async_scene_on(self, scene_id: int) -> None:
        await self._request("POST", f"/scenes/{scene_id}/on")

    async def async_scene_off(self, scene_id: int) -> None:
        await self._request("POST", f"/scenes/{scene_id}/off")

    async def async_scene_level(self, scene_id: int, level: int) -> None:
        await self._request(
            "POST", f"/scenes/{scene_id}/level", json={"level": level}
        )

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT):
                async with self._session.request(
                    method, url, json=json, headers=self._headers
                ) as response:
                    if response.status in (401, 403):
                        raise Esp32CasambiAuthError(
                            f"Controller rejected the API key ({response.status}) "
                            f"for {url}. Check the configured password."
                        )
                    response.raise_for_status()
                    if response.content_type == "application/json":
                        return await response.json()
                    return {}
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Request to %s failed: %s", url, err)
            raise Esp32CasambiApiError(
                f"Error communicating with controller at {url}: {err}"
            ) from err
