"""Constants for the ESP32 Casambi Controller integration."""

DOMAIN = "esp32_casambi"

CONF_HOST = "host"
CONF_PASSWORD = "password"

DEFAULT_PORT = 80
# The akumap fork's GET /api/units now returns real-time on/level/vertical/
# colorTemp (pushed into it from BLE status broadcasts), not just discovery
# data - so a shorter poll interval gives near-live state in HA without
# needing a WebSocket client. 10s is a reasonable balance; the controller's
# HTTP stack is stress-tested for normal polling rates (see upstream README).
DEFAULT_SCAN_INTERVAL = 10  # seconds

# Must match API_TOKEN_PREFIX in config.h on the firmware. The API key sent
# in the X-API-Key header is derived as:
#   hex( SHA-256( API_TOKEN_PREFIX + casambi_network_password ) )
# The firmware only enforces auth when a Casambi password is configured on
# the controller itself (empty password = open API, for pre-auth setups).
API_TOKEN_PREFIX = "casambi-api:"

# Casambi levels are 0-255, which happens to match Home Assistant's
# native ColorMode.BRIGHTNESS scale, so no rescaling is needed.
CASAMBI_MAX_LEVEL = 255
