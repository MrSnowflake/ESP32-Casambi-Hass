"""Constants for the ESP32 Casambi Controller integration."""

DOMAIN = "esp32_casambi"

CONF_HOST = "host"
CONF_PASSWORD = "password"

DEFAULT_PORT = 80

# The WebSocket push (ws://<host>/ws) is now the primary source of live
# state - sub-100ms latency per the firmware's own README. This interval
# is only a REST fallback: used while the WebSocket hasn't connected yet
# (e.g. right after HA startup) or has dropped and is reconnecting.
FALLBACK_SCAN_INTERVAL = 10  # seconds

WS_PATH = "/ws"

# WebSocket reconnect backoff (seconds). Mirrors the firmware's own BLE
# reconnect backoff shape (BLE_RECONNECT_INTERVAL_MS / _MAX_BACKOFF_MS in
# config.h) rather than inventing an unrelated scheme.
WS_RECONNECT_INITIAL_S = 5
WS_RECONNECT_MAX_S = 60

# aiohttp WebSocket heartbeat (seconds) - detects a dead TCP connection
# promptly instead of waiting on the OS-level timeout.
WS_HEARTBEAT_S = 30

# Must match API_TOKEN_PREFIX in config.h on the firmware. The API key sent
# in the X-API-Key header is derived as:
#   hex( SHA-256( API_TOKEN_PREFIX + casambi_network_password ) )
# The firmware only enforces auth when a Casambi password is configured on
# the controller itself (empty password = open API, for pre-auth setups).
# The same header authenticates both REST requests and the /ws upgrade.
API_TOKEN_PREFIX = "casambi-api:"

# Casambi levels are 0-255, which happens to match Home Assistant's
# native ColorMode.BRIGHTNESS scale, so no rescaling is needed.
CASAMBI_MAX_LEVEL = 255
