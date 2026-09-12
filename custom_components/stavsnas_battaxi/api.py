"""Client for the public Stavsnäs Båttaxi web API."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponseError, ClientSession
from yarl import URL

from .const import API_BASE_URL, API_TIMEOUT, TIMEZONE
from .models import BattaxiDeparture, BattaxiLine, BattaxiPier


class BattaxiApiError(Exception):
    """Base error for the Båttaxi API."""


class BattaxiConnectionError(BattaxiApiError):
    """The API could not be reached (timeout, DNS, connection reset...)."""


class BattaxiRateLimitError(BattaxiApiError):
    """The API answered HTTP 429."""


class BattaxiInvalidResponseError(BattaxiApiError):
    """The API answered with malformed JSON or an unexpected schema."""


def _require(item: Any, key: str, what: str) -> Any:
    """Return item[key] or raise a schema error naming the missing field."""
    if not isinstance(item, dict) or item.get(key) is None:
        raise BattaxiInvalidResponseError(f"{what} is missing required field '{key}'")
    return item[key]


def _items(payload: Any, what: str) -> list[Any]:
    """Return payload['items'] as a list or raise a schema error."""
    if not isinstance(payload, dict):
        raise BattaxiInvalidResponseError(f"{what} response is not a JSON object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise BattaxiInvalidResponseError(f"{what} response has no 'items' list")
    return items


def _optional_int(item: dict[str, Any], key: str) -> int | None:
    """Return item[key] as int, or None when absent/null/not numeric."""
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _parse_clock(value: Any, what: str) -> time:
    """Parse 'HH:MM' into a time."""
    if not isinstance(value, str):
        raise BattaxiInvalidResponseError(f"{what} is not a string: {value!r}")
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as err:
        raise BattaxiInvalidResponseError(f"{what} is not HH:MM: {value!r}") from err


def parse_piers(payload: Any) -> list[BattaxiPier]:
    """Parse the /api/public/piers response."""
    return [
        BattaxiPier(
            id=str(_require(item, "id", "pier")),
            name=str(_require(item, "name", "pier")),
        )
        for item in _items(payload, "piers")
    ]


def parse_lines(payload: Any) -> list[BattaxiLine]:
    """Parse the /api/public/lines response."""
    lines: list[BattaxiLine] = []
    for item in _items(payload, "lines"):
        stops = _require(item, "stops", "line")
        if not isinstance(stops, list):
            raise BattaxiInvalidResponseError("line 'stops' is not a list")
        lines.append(
            BattaxiLine(
                id=str(_require(item, "id", "line")),
                name=str(_require(item, "name", "line")),
                stops=tuple(str(stop) for stop in stops),
            )
        )
    return lines


def parse_departures(
    payload: Any,
    *,
    origin_id: str,
    destination_id: str,
    day: date,
    tz: tzinfo,
) -> list[BattaxiDeparture]:
    """Parse the /api/search response for one day into aware datetimes."""
    departures: list[BattaxiDeparture] = []
    for item in _items(payload, "search"):
        departure_clock = _parse_clock(
            _require(item, "departureTime", "departure"), "departureTime"
        )
        arrival_clock = _parse_clock(
            _require(item, "arrivalTime", "departure"), "arrivalTime"
        )
        departure = datetime.combine(day, departure_clock, tzinfo=tz)
        arrival = datetime.combine(day, arrival_clock, tzinfo=tz)
        if arrival < departure:
            # Arrival clock time wrapped past midnight.
            arrival += timedelta(days=1)
        departures.append(
            BattaxiDeparture(
                id=str(_require(item, "departureId", "departure")),
                line_id=str(_require(item, "lineId", "departure")),
                line_name=str(_require(item, "lineName", "departure")),
                origin_id=origin_id,
                destination_id=destination_id,
                departure=departure,
                arrival=arrival,
                duration_minutes=_optional_int(item, "durationMinutes"),
                available_seats=_optional_int(item, "availableSeats"),
                bookable=bool(_require(item, "bookable", "departure")),
            )
        )
    return departures


class BattaxiApi:
    """Async client for api.battaxi.se using a shared aiohttp session."""

    def __init__(
        self,
        session: ClientSession,
        *,
        base_url: str = API_BASE_URL,
        timezone: tzinfo | None = None,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._base_url = URL(base_url)
        self.timezone: tzinfo = timezone or ZoneInfo(TIMEZONE)

    async def async_get_piers(self) -> list[BattaxiPier]:
        """Fetch all piers."""
        return parse_piers(await self._async_get_json("/api/public/piers"))

    async def async_get_lines(self) -> list[BattaxiLine]:
        """Fetch all lines with their ordered stops."""
        return parse_lines(await self._async_get_json("/api/public/lines"))

    async def async_search(
        self, origin_id: str, destination_id: str, day: date
    ) -> list[BattaxiDeparture]:
        """Fetch departures between two piers on a given day."""
        payload = await self._async_get_json(
            "/api/search",
            {"origin": origin_id, "dest": destination_id, "date": day.isoformat()},
        )
        return parse_departures(
            payload,
            origin_id=origin_id,
            destination_id=destination_id,
            day=day,
            tz=self.timezone,
        )

    async def _async_get_json(
        self, path: str, params: dict[str, str] | None = None
    ) -> Any:
        """GET a JSON document, mapping transport/HTTP errors to our exceptions."""
        url = self._base_url.with_path(path)
        try:
            async with asyncio.timeout(API_TIMEOUT):
                response = await self._session.get(url, params=params)
                if response.status == 429:
                    raise BattaxiRateLimitError("Båttaxi API rate limit hit (HTTP 429)")
                if response.status >= 400:
                    raise BattaxiApiError(
                        f"Båttaxi API returned HTTP {response.status} for {path}"
                    )
                try:
                    return await response.json(content_type=None)
                except ValueError as err:
                    raise BattaxiInvalidResponseError(
                        f"Båttaxi API returned invalid JSON for {path}"
                    ) from err
        except TimeoutError as err:
            raise BattaxiConnectionError(
                f"Timeout talking to Båttaxi API ({path})"
            ) from err
        except ClientResponseError as err:
            raise BattaxiApiError(f"Båttaxi API returned HTTP {err.status}") from err
        except ClientError as err:
            raise BattaxiConnectionError(
                f"Error talking to Båttaxi API: {err}"
            ) from err
