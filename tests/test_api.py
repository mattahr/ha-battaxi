"""Tests for the Båttaxi API client and parsers."""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.stavsnas_battaxi.api import (
    BattaxiApi,
    BattaxiApiError,
    BattaxiConnectionError,
    BattaxiInvalidResponseError,
    BattaxiRateLimitError,
    parse_departures,
    parse_lines,
    parse_piers,
)

from .conftest import (
    LINE_ID,
    LINES_URL,
    PIERS_URL,
    SEARCH_URL,
    STAVSNAS,
    TELEGRAFHOLMEN,
    load_json,
)

TZ = ZoneInfo("Europe/Stockholm")
DAY = date(2026, 9, 12)


def _departure_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "departureId": "x",
        "lineId": LINE_ID,
        "lineName": "Sandhamnslinjen",
        "departureTime": "10:00",
        "arrivalTime": "10:30",
        "bookable": True,
    }
    item.update(overrides)
    return item


def _parse(payload: object, day: date = DAY) -> list:
    return parse_departures(
        payload, origin_id=STAVSNAS, destination_id=TELEGRAFHOLMEN, day=day, tz=TZ
    )


def test_parse_piers() -> None:
    piers = parse_piers(load_json("piers.json"))
    assert len(piers) == 8
    by_id = {p.id: p for p in piers}
    assert by_id[TELEGRAFHOLMEN].name == "Telegrafholmen"


def test_parse_lines_keeps_stop_order() -> None:
    lines = parse_lines(load_json("lines.json"))
    sandhamn = next(line for line in lines if line.id == LINE_ID)
    assert sandhamn.name == "Sandhamnslinjen"
    assert sandhamn.stops[0] == STAVSNAS
    assert sandhamn.stops[-1] == STAVSNAS
    assert len(sandhamn.stops) == 8


def test_parse_departures_builds_aware_datetimes() -> None:
    departures = _parse(load_json("search_with_departures.json"))
    assert [d.id for d in departures] == [
        "6a75c74b29f5bc095722dc30",
        "6a75c74b29f5bc095722dc32",
        "other-line-departure",
    ]
    first = departures[0]
    assert first.departure.isoformat() == "2026-09-12T16:40:00+02:00"
    assert first.arrival.isoformat() == "2026-09-12T17:15:00+02:00"
    assert first.duration_minutes == 35
    assert first.available_seats == 59
    assert first.bookable is False
    assert first.origin_id == STAVSNAS
    assert first.destination_id == TELEGRAFHOLMEN
    assert departures[1].bookable is True


def test_parse_departures_missing_seats_is_none() -> None:
    departures = _parse(load_json("search_missing_seats.json"))
    assert departures[0].available_seats is None
    assert departures[0].duration_minutes is None


def test_parse_departures_arrival_after_midnight_rolls_over() -> None:
    payload = {"items": [_departure_item(departureTime="23:50", arrivalTime="00:20")]}
    (departure,) = _parse(payload)
    assert departure.arrival.date() == DAY + timedelta(days=1)
    assert departure.arrival > departure.departure


@pytest.mark.parametrize(
    ("day", "offset"),
    [(date(2026, 1, 10), "+01:00"), (date(2026, 7, 10), "+02:00")],
)
def test_parse_departures_respects_dst(day: date, offset: str) -> None:
    (departure,) = _parse({"items": [_departure_item()]}, day)
    assert departure.departure.isoformat().endswith(offset)


@pytest.mark.parametrize(
    "payload",
    [
        {"items": [_departure_item(departureId=None)]},
        {"items": [_departure_item(bookable=None)]},
        {"items": [_departure_item(departureTime="25:99")]},
        {"items": [_departure_item(arrivalTime=1030)]},
        {"items": "not-a-list"},
        {"no_items": []},
        [],
    ],
)
def test_parse_departures_rejects_bad_schema(payload: object) -> None:
    with pytest.raises(BattaxiInvalidResponseError):
        _parse(payload)


def test_parse_piers_rejects_missing_name() -> None:
    with pytest.raises(BattaxiInvalidResponseError):
        parse_piers({"items": [{"id": "abc"}]})


def test_parse_lines_rejects_missing_stops() -> None:
    with pytest.raises(BattaxiInvalidResponseError):
        parse_lines({"items": [{"id": "abc", "name": "x"}]})
    with pytest.raises(BattaxiInvalidResponseError):
        parse_lines({"items": [{"id": "abc", "name": "x", "stops": "a,b"}]})


async def test_client_fetches_and_parses(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(PIERS_URL, json=load_json("piers.json"))
    aioclient_mock.get(LINES_URL, json=load_json("lines.json"))
    aioclient_mock.get(
        f"{SEARCH_URL}?origin={STAVSNAS}&dest={TELEGRAFHOLMEN}&date=2026-09-12",
        json=load_json("search_with_departures.json"),
    )
    api = BattaxiApi(async_get_clientsession(hass), timezone=TZ)

    assert len(await api.async_get_piers()) == 8
    assert len(await api.async_get_lines()) == 2
    departures = await api.async_search(STAVSNAS, TELEGRAFHOLMEN, DAY)
    assert len(departures) == 3
    assert aioclient_mock.call_count == 3


async def test_client_empty_search_is_not_an_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(SEARCH_URL, json=load_json("search_empty.json"))
    api = BattaxiApi(async_get_clientsession(hass), timezone=TZ)
    assert await api.async_search(STAVSNAS, TELEGRAFHOLMEN, DAY) == []


@pytest.mark.parametrize(
    ("mock_kwargs", "expected"),
    [
        ({"exc": TimeoutError()}, BattaxiConnectionError),
        ({"exc": ClientError("boom")}, BattaxiConnectionError),
        ({"status": 429}, BattaxiRateLimitError),
        ({"status": 500}, BattaxiApiError),
        (
            {"status": 400, "json": {"error": "querystring/date Required"}},
            BattaxiApiError,
        ),
        ({"text": "<html>not json</html>"}, BattaxiInvalidResponseError),
        ({"json": {"items": [{"id": "only-id"}]}}, BattaxiInvalidResponseError),
    ],
)
async def test_client_error_mapping(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_kwargs: dict,
    expected: type[BattaxiApiError],
) -> None:
    aioclient_mock.get(PIERS_URL, **mock_kwargs)
    api = BattaxiApi(async_get_clientsession(hass), timezone=TZ)
    with pytest.raises(expected):
        await api.async_get_piers()
