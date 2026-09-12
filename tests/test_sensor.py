"""Tests for the sensor and binary sensor entities."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.stavsnas_battaxi.const import DOMAIN, UPDATE_INTERVAL

from .conftest import LINES_URL, PIERS_URL, SEARCH_URL, load_json


async def setup_entry(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def get_state(hass: HomeAssistant, platform: str, key: str) -> State:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, f"test-entry_{key}")
    assert entity_id is not None, f"{platform} {key} not registered"
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def test_all_entities_with_upcoming_departure(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    await setup_entry(hass, config_entry)

    next_departure = get_state(hass, "sensor", "next_departure")
    assert next_departure.state == "2026-09-12T17:10:00+00:00"
    assert next_departure.attributes["device_class"] == "timestamp"
    assert next_departure.attributes["line"] == "Sandhamnslinjen"
    assert next_departure.attributes["origin"] == "Stavsnäs"
    assert next_departure.attributes["destination"] == "Telegrafholmen"
    assert next_departure.attributes["departure_id"] == "6a75c74b29f5bc095722dc32"
    assert (
        next_departure.attributes["friendly_name"]
        == "Stavsnäs → Telegrafholmen Next departure"
    )

    assert (
        get_state(hass, "sensor", "next_arrival").state == "2026-09-12T17:45:00+00:00"
    )
    assert (
        get_state(hass, "sensor", "next_departure_text").state
        == "19:10 Stavsnäs → 19:45 Telegrafholmen · 60 lediga"
    )
    assert get_state(hass, "sensor", "available_seats").state == "60"
    assert get_state(hass, "binary_sensor", "bookable").state == STATE_ON

    departures_today = get_state(hass, "sensor", "departures_today")
    assert departures_today.state == "1"
    assert departures_today.attributes["departures"] == [
        {
            "departure": "19:10",
            "arrival": "19:45",
            "available_seats": 60,
            "bookable": True,
        }
    ]
    assert (
        get_state(hass, "sensor", "departures_today_text").state == "19:10 – 60 platser"
    )


async def test_device_is_a_service_device_for_the_route(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    await setup_entry(hass, config_entry)

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "test-entry"), config_entry.entry_id
    )
    assert device is not None
    assert device.name == "Stavsnäs → Telegrafholmen"
    assert device.manufacturer == "Stavsnäs Båttaxi"
    assert device.model == "Sandhamnslinjen"
    assert device.entry_type is dr.DeviceEntryType.SERVICE


async def test_not_bookable_is_off_not_cancelled(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    aioclient_mock.get(SEARCH_URL, json=load_json("search_not_bookable.json"))
    await setup_entry(hass, config_entry)

    assert get_state(hass, "binary_sensor", "bookable").state == STATE_OFF
    assert get_state(hass, "sensor", "available_seats").state == "0"
    assert (
        get_state(hass, "sensor", "next_departure").state == "2026-09-12T17:10:00+00:00"
    )
    assert (
        get_state(hass, "sensor", "next_departure_text").state
        == "19:10 Stavsnäs → 19:45 Telegrafholmen · 0 lediga · ej bokningsbar"
    )


async def test_missing_seats_is_unknown(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    aioclient_mock.get(SEARCH_URL, json=load_json("search_missing_seats.json"))
    await setup_entry(hass, config_entry)

    assert get_state(hass, "sensor", "available_seats").state == STATE_UNKNOWN
    assert (
        get_state(hass, "sensor", "next_departure_text").state
        == "19:10 Stavsnäs → 19:45 Telegrafholmen"
    )


async def test_no_departures_at_all(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    aioclient_mock.get(SEARCH_URL, json=load_json("search_empty.json"))
    await setup_entry(hass, config_entry)

    assert get_state(hass, "sensor", "next_departure").state == STATE_UNKNOWN
    assert get_state(hass, "sensor", "next_arrival").state == STATE_UNKNOWN
    assert get_state(hass, "sensor", "next_departure_text").state == STATE_UNKNOWN
    assert get_state(hass, "sensor", "available_seats").state == STATE_UNKNOWN
    assert get_state(hass, "binary_sensor", "bookable").state == STATE_UNKNOWN
    assert get_state(hass, "sensor", "departures_today").state == "0"
    assert (
        get_state(hass, "sensor", "departures_today_text").state
        == "Inga fler avgångar idag"
    )


async def test_entities_unavailable_after_api_failure(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    await setup_entry(hass, config_entry)
    assert get_state(hass, "sensor", "next_departure").state != STATE_UNAVAILABLE

    mock_api.clear_requests()
    mock_api.get(SEARCH_URL, status=500)
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert get_state(hass, "sensor", "next_departure").state == STATE_UNAVAILABLE
    assert get_state(hass, "binary_sensor", "bookable").state == STATE_UNAVAILABLE

    # Recovers on the next successful poll without a restart.
    mock_api.clear_requests()
    mock_api.get(PIERS_URL, json=load_json("piers.json"))
    mock_api.get(LINES_URL, json=load_json("lines.json"))
    mock_api.get(SEARCH_URL, json=load_json("search_with_departures.json"))
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        get_state(hass, "sensor", "next_departure").state == "2026-09-12T17:10:00+00:00"
    )
