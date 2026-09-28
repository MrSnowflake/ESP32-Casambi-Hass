# ESP32 Casambi Controller for Home Assistant

Custom Home Assistant integration for the [akumap/esp32-casambi](https://github.com/akumap/esp32-casambi) firmware (a fork of [lian/esp32-casambi](https://github.com/lian/esp32-casambi)) — an offline ESP32 BLE controller for Casambi lighting.

Each Casambi unit is exposed as a `light` entity with:

- **On/off** and **brightness**, pushed live over the controller's WebSocket (`ws://<host>/ws`, sub-100ms latency) — reflects changes made from the official Casambi app, scene timers, sensors, or other controllers, not just commands sent from Home Assistant. REST polling (`GET /api/units`) is used as a fallback while the WebSocket is disconnected or hasn't connected yet.
- **Color temperature**, for fixtures that report `cctMin`/`cctMax` (converted to Kelvin)
- **Auth support** — the `X-API-Key` token is derived from your Casambi network password, matching the controller's authentication scheme (used for both REST and the WebSocket upgrade)

## Requirements

- An ESP32 running the [akumap/esp32-casambi](https://github.com/akumap/esp32-casambi) firmware (v1.3+ of the ESP↔FHEM interface), provisioned and reachable on your network
- Home Assistant 2024.8 or newer

## Installation via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=https%3A%2F%2Fgithub.com%2Fdrschnalli%2FESP32-Casambi-Hass%2Ftree%2Fmain&owner=drschnalli&category=integration)

Or Manually

1. HACS → the three-dot menu (top right) → **Custom repositories**
2. Add this repository URL, category **Integration**
3. Find **ESP32 Casambi Controller** in HACS and install it
4. Restart Home Assistant
5. **Settings → Devices & Services → Add Integration** → search for "ESP32 Casambi"
6. Enter the controller's IP address and (if configured on the controller) its Casambi network password

## What this integration does *not* do (yet)

- No vertical light distribution or RGB color control exposed as entities (these don't map cleanly onto Home Assistant's light model).
- No scene or group entities — only individual units.

Contributions welcome.

## License

MIT
