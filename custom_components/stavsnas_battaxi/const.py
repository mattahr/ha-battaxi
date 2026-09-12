"""Constants for the Stavsnäs Båttaxi integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "stavsnas_battaxi"
MANUFACTURER: Final = "Stavsnäs Båttaxi"
CONFIGURATION_URL: Final = "https://www.battaxi.se/"

API_BASE_URL: Final = "https://api.battaxi.se"
API_TIMEOUT: Final = 15  # seconds per request
TIMEZONE: Final = "Europe/Stockholm"

UPDATE_INTERVAL: Final = timedelta(minutes=5)
FUTURE_CACHE_TTL: Final = timedelta(hours=6)
MAX_LOOKAHEAD_DAYS: Final = 14

PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.SENSOR]

# Config entry data keys
CONF_LINE_ID: Final = "line_id"
CONF_LINE_NAME: Final = "line_name"
CONF_ORIGIN_ID: Final = "origin_id"
CONF_ORIGIN_NAME: Final = "origin_name"
CONF_DESTINATION_ID: Final = "destination_id"
CONF_DESTINATION_NAME: Final = "destination_name"

# Config flow form field keys
CONF_LINE: Final = "line"
CONF_ORIGIN: Final = "origin"
CONF_DESTINATION: Final = "destination"
