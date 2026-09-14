"""The Stavsnäs Båttaxi integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import BattaxiApi
from .const import PLATFORMS, TIMEZONE
from .coordinator import BattaxiConfigEntry, BattaxiCoordinator
from .models import BattaxiRoute


async def async_setup_entry(hass: HomeAssistant, entry: BattaxiConfigEntry) -> bool:
    """Set up one configured route from a config entry."""
    route = BattaxiRoute.from_config(entry.data)
    api = BattaxiApi(
        async_get_clientsession(hass),
        timezone=await dt_util.async_get_time_zone(TIMEZONE),
    )
    coordinator = BattaxiCoordinator(hass, entry, api, route)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BattaxiConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
