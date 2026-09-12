"""Tests for config entry diagnostics."""

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.stavsnas_battaxi.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import ROUTE_DATA


async def test_diagnostics(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["route"] == ROUTE_DATA
    assert diagnostics["last_update_success"] is True
    assert diagnostics["last_update"] == "2026-09-12T17:00:00+02:00"
    assert diagnostics["today"] == "2026-09-12"
    assert diagnostics["departures_today"] == 1
    assert diagnostics["next_departure"]["departure"] == "2026-09-12T19:10:00+02:00"
    assert diagnostics["next_departure"]["bookable"] is True
    assert diagnostics["cached_dates"] == []
