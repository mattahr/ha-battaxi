"""Tests for the departure coordinator, cache and lookahead."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.stavsnas_battaxi.api import BattaxiApi
from custom_components.stavsnas_battaxi.const import MAX_LOOKAHEAD_DAYS
from custom_components.stavsnas_battaxi.coordinator import BattaxiCoordinator
from custom_components.stavsnas_battaxi.models import BattaxiRoute

from .conftest import ROUTE_DATA, SEARCH_URL, STAVSNAS, TELEGRAFHOLMEN, load_json

TZ = ZoneInfo("Europe/Stockholm")


def search_url(day: str) -> str:
    return f"{SEARCH_URL}?origin={STAVSNAS}&dest={TELEGRAFHOLMEN}&date={day}"


async def make_coordinator(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> BattaxiCoordinator:
    config_entry.add_to_hass(hass)
    api = BattaxiApi(async_get_clientsession(hass), timezone=TZ)
    return BattaxiCoordinator(
        hass, config_entry, api, BattaxiRoute.from_config(ROUTE_DATA)
    )


async def test_next_departure_today_filters_passed_and_other_lines(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    aioclient_mock.get(
        search_url("2026-09-12"), json=load_json("search_with_departures.json")
    )
    coordinator = await make_coordinator(hass, config_entry)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    data = coordinator.data
    assert data.today.isoformat() == "2026-09-12"
    assert [d.id for d in data.departures_today] == ["6a75c74b29f5bc095722dc32"]
    assert data.next_departure is not None
    assert data.next_departure.departure.isoformat() == "2026-09-12T19:10:00+02:00"
    assert aioclient_mock.call_count == 1


async def test_departure_exactly_now_is_not_passed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 16:40:00+02:00")
    aioclient_mock.get(
        search_url("2026-09-12"), json=load_json("search_with_departures.json")
    )
    coordinator = await make_coordinator(hass, config_entry)

    await coordinator.async_refresh()

    assert [d.id for d in coordinator.data.departures_today] == [
        "6a75c74b29f5bc095722dc30",
        "6a75c74b29f5bc095722dc32",
    ]


async def test_rolls_over_to_next_day_and_caches_it(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    # Noon, so the 6 h cache TTL test below stays on the same calendar day.
    freezer.move_to("2026-09-12 12:00:00+02:00")
    aioclient_mock.get(search_url("2026-09-12"), json=load_json("search_empty.json"))
    aioclient_mock.get(search_url("2026-09-13"), json=load_json("search_empty.json"))
    aioclient_mock.get(
        search_url("2026-09-14"), json=load_json("search_not_bookable.json")
    )
    coordinator = await make_coordinator(hass, config_entry)

    await coordinator.async_refresh()

    data = coordinator.data
    assert data.departures_today == []
    assert data.next_departure is not None
    assert data.next_departure.departure.isoformat() == "2026-09-14T19:10:00+02:00"
    assert aioclient_mock.call_count == 3

    # Second poll within the cache TTL only re-fetches today.
    freezer.tick(timedelta(minutes=5))
    await coordinator.async_refresh()
    assert aioclient_mock.call_count == 4
    assert (
        coordinator.data.next_departure.departure.isoformat()
        == "2026-09-14T19:10:00+02:00"
    )

    # After the TTL the future days are fetched again.
    freezer.tick(timedelta(hours=6, minutes=1))
    await coordinator.async_refresh()
    assert aioclient_mock.call_count == 7


async def test_no_traffic_within_window_gives_no_next_departure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 20:00:00+02:00")
    aioclient_mock.get(SEARCH_URL, json=load_json("search_empty.json"))
    coordinator = await make_coordinator(hass, config_entry)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data.next_departure is None
    assert coordinator.data.departures_today == []
    assert aioclient_mock.call_count == 1 + MAX_LOOKAHEAD_DAYS


async def test_midnight_rollover_drops_stale_cache(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 23:00:00+02:00")
    aioclient_mock.get(search_url("2026-09-12"), json=load_json("search_empty.json"))
    aioclient_mock.get(
        search_url("2026-09-13"), json=load_json("search_not_bookable.json")
    )
    coordinator = await make_coordinator(hass, config_entry)
    await coordinator.async_refresh()
    assert coordinator.data.next_departure.departure.date().isoformat() == (
        "2026-09-13"
    )
    assert [entry["date"] for entry in coordinator.cache_summary()] == ["2026-09-13"]

    freezer.move_to("2026-09-13 01:00:00+02:00")
    await coordinator.async_refresh()

    # 2026-09-13 is now "today" and is always re-fetched, not served from cache.
    assert coordinator.data.today.isoformat() == "2026-09-13"
    assert [d.id for d in coordinator.data.departures_today] == [
        "6a75c74b29f5bc095722dc99"
    ]
    assert coordinator.cache_summary() == []


@pytest.mark.parametrize(
    "mock_kwargs",
    [{"status": 500}, {"status": 429}, {"exc": TimeoutError()}, {"text": "nope"}],
)
async def test_api_errors_become_update_failed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    mock_kwargs: dict,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    aioclient_mock.get(SEARCH_URL, **mock_kwargs)
    coordinator = await make_coordinator(hass, config_entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
