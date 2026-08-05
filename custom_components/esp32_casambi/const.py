"""Constants for the ESP32 Casambi integration."""
from __future__ import annotations

DOMAIN = "esp32_casambi"

CONF_HOST = "host"
CONF_PASSWORD = "password"

DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 10

API_TOKEN_PREFIX = "casambi-api:"
API_KEY_HEADER = "X-API-Key"
CASAMBI_MAX_LEVEL = 255

PLATFORMS = ["light", "scene"]
