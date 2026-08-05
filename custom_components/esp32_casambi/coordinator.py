"""DataUpdateCoordinator for the ESP32 Casambi Controller.

Live unit state is primarily pushed via the controller's WebSocket
(ws://<host>/ws): a `hello` message with a full snapshot on connect, then
`unit_state` on every change - originating from HA's own commands, the
official Casambi app, scene timers, sensors, or another controller. This
gives sub-100ms update latency instead of waiting out a poll interval.

GET /api/units (REST) is kept as a fallback, used only while the
WebSocket hasn't connected yet (e.g. right after HA startup) or has
dropped and is reconnecting. Once the WebSocket is up, REST polling is
switched off entirely to avoid double-fetching.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import Esp32CasambiApiError, Esp32CasambiAuthError, Esp32CasambiClient
from .const import (
    DOMAIN,
    FALLBACK_SCAN_INTERVAL,
    WS_HEARTBEAT_S,
    WS_RECONNECT_INITIAL_S,
    WS_RECONNECT_MAX_S,
)

_LOGGER = logging.getLogger(__name__)


class Esp32CasambiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds live unit state, fed by WebSocket push with REST fallback."""

    def __init__(self, hass: HomeAssistant, client: Esp32CasambiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=FALLBACK_SCAN_INTERVAL),
        )
        self.client = client
        self._ws_connected = False
        self._ws_task: asyncio.Task | None = None
        self._stopping = False

    # -- REST fallback -----------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """REST fetch. Only actually scheduled while the WebSocket is not
        connected - see _set_ws_connected()."""
        try:
            units = await self.client.async_get_units()
        except Esp32CasambiAuthError as err:
            # Password was changed on the controller (or auth was newly
            # enabled) since this entry was set up - prompt for re-auth
            # instead of silently failing forever (REST *and* WebSocket
            # would both be rejecting the same stale token).
            raise ConfigEntryAuthFailed(str(err)) from err
        except Esp32CasambiApiError as err:
            _LOGGER.debug("REST fallback fetch failed: %s", err)
            return self.data or {"units": []}

        return {"units": units}

    # -- WebSocket push ------------------------------------------------

    def start_websocket(self) -> None:
        """Start the background WebSocket listener.

        Call once after the first REST refresh has populated initial
        data, so entities exist immediately even if the WS handshake is
        briefly delayed.
        """
        if self._ws_task is None:
            self._ws_task = self.hass.async_create_background_task(
                self._ws_loop(), name=f"{DOMAIN}_websocket"
            )

    async def async_stop(self) -> None:
        """Called on config entry unload."""
        self._stopping = True
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

    async def _ws_loop(self) -> None:
        backoff = WS_RECONNECT_INITIAL_S
        while not self._stopping:
            try:
                await self._ws_connect_once()
                # A clean session (no exception) still ends when the
                # controller closes the socket - reset backoff so a
                # single transient drop doesn't escalate the wait time.
                backoff = WS_RECONNECT_INITIAL_S
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - any failure just reconnects
                _LOGGER.debug("WebSocket session ended: %s", err)
            finally:
                self._set_ws_connected(False)

            if self._stopping:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, WS_RECONNECT_MAX_S)

    async def _ws_connect_once(self) -> None:
        async with self.client.session.ws_connect(
            self.client.ws_url,
            headers=self.client.headers,
            heartbeat=WS_HEARTBEAT_S,
        ) as ws:
            _LOGGER.debug("WebSocket connected to %s", self.client.ws_url)
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._handle_message(msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    break

    def _handle_message(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            _LOGGER.debug("Ignoring non-JSON WebSocket message")
            return

        msg_type = message.get("type")

        if msg_type == "hello":
            # Full snapshot - this is also our "connected" signal, since
            # it's the first message the controller sends on upgrade.
            self._set_ws_connected(True)
            self.async_set_updated_data({"units": message.get("units", [])})
        elif msg_type == "unit_state":
            self._merge_unit_state(message)
        elif msg_type == "connection_state":
            # This is the controller's BLE link to the Casambi mesh
            # flapping, not our WebSocket connection to the controller -
            # informational only, per-unit `online` already carries this.
            _LOGGER.debug(
                "Controller BLE link state: connected=%s reason=%s",
                message.get("connected"),
                message.get("reason"),
            )
        else:
            _LOGGER.debug("Unhandled WebSocket message type: %s", msg_type)

    def _merge_unit_state(self, message: dict[str, Any]) -> None:
        unit_id = message.get("id")
        if unit_id is None:
            return

        units = list((self.data or {}).get("units", []))
        for index, unit in enumerate(units):
            if unit.get("id") == unit_id:
                units[index] = {**unit, **message}
                break
        else:
            # Not in the last hello snapshot (e.g. hello was truncated at
            # WS_HELLO_MAX_UNITS, or this unit appeared afterwards) - add
            # it rather than silently dropping the update.
            units.append(message)

        self.async_set_updated_data({"units": units})

    def _set_ws_connected(self, connected: bool) -> None:
        if connected == self._ws_connected:
            return
        self._ws_connected = connected

        if connected:
            # WebSocket is now authoritative and pushes on every change -
            # stop REST polling rather than double-fetching. Takes effect
            # after the currently-scheduled REST tick (if any) completes.
            self.update_interval = None
        else:
            # Resume REST polling immediately as a fallback until the
            # WebSocket reconnects, instead of waiting out a full
            # interval with stale data.
            self.update_interval = timedelta(seconds=FALLBACK_SCAN_INTERVAL)
            self.hass.async_create_task(self.async_request_refresh())
