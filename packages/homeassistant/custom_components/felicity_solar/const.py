"""Constants for the Felicity Solar integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "felicity_solar"

#: Configuration keys stored in the config entry.
CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_PLANT_ID: Final = "plant_id"
CONF_PLANT_NAME: Final = "plant_name"
CONF_DEVICE_SERIALS: Final = "device_serials"
CONF_SCAN_DEVICES: Final = "scan_devices"

#: Options.
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_USE_WEBSOCKET: Final = "use_websocket"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_ENABLE_PLANT_FLOW: Final = "enable_plant_flow"
CONF_ENABLE_ALERTS: Final = "enable_alerts"
CONF_API_NODE: Final = "api_node"

#: Defaults.
DEFAULT_SCAN_INTERVAL: Final = 60
DEFAULT_POLL_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 3600

#: The base URLs of the two known FSolar nodes.
API_URLS: Final[dict[str, str]] = {
    "INT": "https://shine-api.felicitysolar.com",
    "EU": "https://shine-api.felicitysolar.com",
}
WS_URLS: Final[dict[str, str]] = {
    "INT": "wss://shine-api.felicitysolar.com",
    "EU": "wss://shine-api.felicitysolar.com",
}

DEFAULT_SCAN_INTERVAL_TIMEDELTA: Final = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

#: The device classes the integration knows how to describe.
SUPPORTED_PRODUCT_TYPES: Final = frozenset(
    {"HIGH_FREQUENCY_INVERTER", "LITHIUM_BATTERY_PACK", "CONTROLLER"}
)
