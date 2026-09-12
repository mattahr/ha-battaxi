# Stavsnäs Båttaxi Home Assistant Integration – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only HACS custom integration `stavsnas_battaxi` that lets a user pick a directed route (line → from pier → to pier) in a config flow and exposes the next departure, today's departures and related data as sensors, plus a Docker-based dev environment started by F5 in VS Code.

**Architecture:** `api.py` wraps `api.battaxi.se` and parses JSON into frozen dataclasses (`models.py`); `routes.py` derives valid directed routes from a line's ordered stop list; `coordinator.py` (DataUpdateCoordinator, 5 min) fetches today's departures every poll and looks ahead up to 14 days with a 6 h per-date cache; `sensor.py`/`binary_sensor.py` are thin `CoordinatorEntity` subclasses that read `coordinator.data`; `formatting.py` builds the Swedish display strings. One config entry per route, device identified by `entry_id`.

**Tech Stack:** Python 3.14, Home Assistant 2026.9, aiohttp (HA shared session), voluptuous, `pytest-homeassistant-custom-component==0.13.365` (pytest, `aioclient_mock`, `freezer`), `uv`, ruff, Docker Compose + debugpy.

**Spec:** `docs/stavsnas_battaxi_home_assistant_design.md` (especially §31 for verified API schemas and decisions).

## Global Constraints

- Domain: `stavsnas_battaxi`; display name `Stavsnäs Båttaxi`; manufacturer `Stavsnäs Båttaxi`.
- Base URL `https://api.battaxi.se`; endpoints `/api/public/piers`, `/api/public/lines`, `/api/search?origin&dest&date`. `availability` is NOT used.
- Polling: 5 minutes. Today is always re-fetched; future dates cached 6 h (also empty ones); lookahead max 14 days, only when today has no remaining departures.
- All datetimes timezone-aware in `Europe/Stockholm`; "now" via `dt_util.now(tz)`.
- `bookable=false` is never interpreted as cancelled. No cancelled/delay/minutes-until sensors.
- `availableSeats` missing → sensor `unknown`, never `0`.
- Config entry data keys: `line_id`, `line_name`, `origin_id`, `origin_name`, `destination_id`, `destination_name`. Entry unique_id `<line_id>:<origin_id>:<destination_id>`. Entry title `<origin_name> → <destination_name>`.
- Device identifier `(DOMAIN, entry.entry_id)`, `entry_type=SERVICE`, model = line name. Entity unique_id `<entry_id>_<key>`. `_attr_has_entity_name = True`, names via translation keys (sv + en).
- Sensors never do HTTP; only the coordinator calls the API. Coordinator raises `UpdateFailed` on any `BattaxiApiError`.
- Sensor state strings are Swedish as in spec §10.2/§10.7 and must be ≤ 255 chars.
- Code, comments, README in English. Type-annotated, fully async, ruff-clean (`uv run ruff check .`).
- Tests: `uv run pytest` from repo root; `enable_custom_integrations` autouse.
- No git repository exists yet – commit steps are omitted; the user decides on `git init`.
- Dev env: `ghcr.io/home-assistant/home-assistant:stable`, ports `HA_PORT` (8123) and `DEBUGPY_PORT` (5678) overridable via `.env`; `dev/ha.sh up` must refuse to start when a port is taken by something else and say what holds it.

## File Structure

```
custom_components/stavsnas_battaxi/
├── __init__.py          # async_setup_entry / async_unload_entry, builds api + coordinator
├── api.py               # BattaxiApi + exceptions + JSON → model parsing
├── binary_sensor.py     # bookable
├── config_flow.py       # user + reconfigure flow: line → origin → destination
├── const.py             # constants and config keys
├── coordinator.py       # BattaxiCoordinator, BattaxiData, per-date cache
├── diagnostics.py       # config entry diagnostics
├── entity.py            # BattaxiEntity base (device info, unique_id)
├── formatting.py        # Swedish display strings for text sensors
├── manifest.json
├── models.py            # BattaxiPier, BattaxiLine, BattaxiRoute, BattaxiDeparture
├── routes.py            # valid directed routes from ordered stop lists
├── sensor.py            # six sensors
├── strings.json
└── translations/{en,sv}.json
tests/
├── conftest.py
├── fixtures/{piers,lines,search_with_departures,search_empty,search_not_bookable,search_missing_seats}.json
├── test_api.py, test_routes.py, test_formatting.py, test_coordinator.py,
│   test_config_flow.py, test_init.py, test_sensor.py, test_diagnostics.py
dev/ha.sh, dev/config/configuration.yaml, docker-compose.yml, .env.example
.vscode/{launch,tasks,settings,extensions}.json
hacs.json, README.md, LICENSE, .gitignore, .github/workflows/{validate,tests}.yml
```

---

### Task 1: Fixtures, constants, models

**Files:**
- Create: `custom_components/stavsnas_battaxi/__init__.py` (empty placeholder for now – replaced in Task 6)
- Create: `custom_components/stavsnas_battaxi/const.py`
- Create: `custom_components/stavsnas_battaxi/models.py`
- Create: `custom_components/stavsnas_battaxi/manifest.json`
- Create: `tests/__init__.py` (empty), `tests/conftest.py`, `tests/fixtures/*.json`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `BattaxiPier(id, name)`, `BattaxiLine(id, name, stops: tuple[str, ...])`, `BattaxiRoute(line_id, line_name, origin_id, origin_name, destination_id, destination_name)` with `.unique_id`, `.title`, `.as_config()`, `BattaxiRoute.from_config(mapping)`, `BattaxiDeparture(id, line_id, line_name, origin_id, destination_id, departure, arrival, duration_minutes, available_seats, bookable)`.
- Produces constants listed below.

- [ ] **Step 1: Create fixtures from the verified API responses**

`tests/fixtures/piers.json`:

```json
{
  "items": [
    {"id": "6a31a5430bdad9fa1552c74a", "name": "Bullerö", "area": "Bullerö", "canBoard": true, "canAlight": true, "location": {"lat": 59.199625, "lng": 18.84902}},
    {"id": "6a31a5430bdad9fa1552c749", "name": "Idöborg", "area": "Bullerö", "canBoard": true, "canAlight": true, "location": {"lat": 59.204284, "lng": 18.757739}},
    {"id": "6a31a5470bdad9fa1552c80c", "name": "Lökholmen", "area": "Sandhamn", "canBoard": true, "canAlight": true, "location": {"lat": 59.289266, "lng": 18.928826}},
    {"id": "6a31a5470bdad9fa1552c809", "name": "Sandhamn", "area": "Sandhamn", "canBoard": true, "canAlight": true, "location": {"lat": 59.28847, "lng": 18.915528}},
    {"id": "6a31a5430bdad9fa1552c748", "name": "Stavsnäs", "area": "Bullerö", "canBoard": true, "canAlight": true, "location": {"lat": 59.286659, "lng": 18.704942}},
    {"id": "6a31a5470bdad9fa1552c80a", "name": "Telegrafholmen", "area": "Sandhamn", "canBoard": true, "canAlight": true, "location": {"lat": 59.289812379249746, "lng": 18.919855693652714}},
    {"id": "6a31a5470bdad9fa1552c80b", "name": "Trouville", "area": "Sandhamn", "canBoard": true, "canAlight": true, "location": {"lat": 59.280028, "lng": 18.930677}},
    {"id": "6a31a5430bdad9fa1552c762", "name": "Abborrudden - Magnusson", "area": null, "canBoard": true, "canAlight": true, "location": {"lat": 59.206695, "lng": 18.719068}}
  ]
}
```

`tests/fixtures/lines.json`:

```json
{
  "items": [
    {
      "id": "6a31a5430bdad9fa1552c74b",
      "name": "Bullerölinjen",
      "stops": ["6a31a5430bdad9fa1552c748", "6a31a5430bdad9fa1552c749", "6a31a5430bdad9fa1552c74a", "6a31a5430bdad9fa1552c74a", "6a31a5430bdad9fa1552c749", "6a31a5430bdad9fa1552c748"],
      "passengerTypes": [{"key": "adult", "label": {"sv": "Vuxen & Senior", "en": "Adult & Senior"}, "price": 15000}],
      "fuelSurcharge": {"enabled": false, "amount": 0}
    },
    {
      "id": "6a31a5470bdad9fa1552c80d",
      "name": "Sandhamnslinjen",
      "stops": ["6a31a5430bdad9fa1552c748", "6a31a5470bdad9fa1552c809", "6a31a5470bdad9fa1552c80a", "6a31a5470bdad9fa1552c80b", "6a31a5470bdad9fa1552c80c", "6a31a5470bdad9fa1552c80a", "6a31a5470bdad9fa1552c809", "6a31a5430bdad9fa1552c748"],
      "passengerTypes": [{"key": "adult", "label": {"sv": "Vuxen", "en": "Adult"}, "price": 11000}],
      "fuelSurcharge": {"enabled": true, "amount": 2000}
    }
  ]
}
```

`tests/fixtures/search_with_departures.json` (real response for Stavsnäs → Telegrafholmen 2026-09-12, `prices`/`passengerTypes` trimmed, plus one departure on another line that must be filtered out by the coordinator):

```json
{
  "items": [
    {
      "departureId": "6a75c74b29f5bc095722dc30",
      "lineId": "6a31a5470bdad9fa1552c80d",
      "lineName": "Sandhamnslinjen",
      "departureTime": "16:40",
      "arrivalTime": "17:15",
      "durationMinutes": 35,
      "availableSeats": 59,
      "prices": {"adult": 11000},
      "passengerTypes": [{"key": "adult", "label": {"sv": "Vuxen", "en": "Adult"}, "price": 11000}],
      "fuelSurcharge": {"enabled": true, "amount": 2000},
      "boardStopIndex": 0,
      "alightStopIndex": 2,
      "bookable": false
    },
    {
      "departureId": "6a75c74b29f5bc095722dc32",
      "lineId": "6a31a5470bdad9fa1552c80d",
      "lineName": "Sandhamnslinjen",
      "departureTime": "19:10",
      "arrivalTime": "19:45",
      "durationMinutes": 35,
      "availableSeats": 60,
      "prices": {"adult": 11000},
      "passengerTypes": [{"key": "adult", "label": {"sv": "Vuxen", "en": "Adult"}, "price": 11000}],
      "fuelSurcharge": {"enabled": true, "amount": 2000},
      "boardStopIndex": 0,
      "alightStopIndex": 2,
      "bookable": true
    },
    {
      "departureId": "other-line-departure",
      "lineId": "6a31a5430bdad9fa1552c74b",
      "lineName": "Bullerölinjen",
      "departureTime": "18:00",
      "arrivalTime": "18:30",
      "durationMinutes": 30,
      "availableSeats": 10,
      "boardStopIndex": 0,
      "alightStopIndex": 1,
      "bookable": true
    }
  ]
}
```

`tests/fixtures/search_empty.json`:

```json
{"items": []}
```

`tests/fixtures/search_not_bookable.json`:

```json
{
  "items": [
    {
      "departureId": "6a75c74b29f5bc095722dc99",
      "lineId": "6a31a5470bdad9fa1552c80d",
      "lineName": "Sandhamnslinjen",
      "departureTime": "19:10",
      "arrivalTime": "19:45",
      "durationMinutes": 35,
      "availableSeats": 0,
      "boardStopIndex": 0,
      "alightStopIndex": 2,
      "bookable": false
    }
  ]
}
```

`tests/fixtures/search_missing_seats.json`:

```json
{
  "items": [
    {
      "departureId": "6a75c74b29f5bc095722dc98",
      "lineId": "6a31a5470bdad9fa1552c80d",
      "lineName": "Sandhamnslinjen",
      "departureTime": "19:10",
      "arrivalTime": "19:45",
      "boardStopIndex": 0,
      "alightStopIndex": 2,
      "bookable": true
    }
  ]
}
```

- [ ] **Step 2: Write `const.py`**

```python
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
```

- [ ] **Step 3: Write `manifest.json`**

```json
{
  "domain": "stavsnas_battaxi",
  "name": "Stavsnäs Båttaxi",
  "codeowners": ["@mattahr"],
  "config_flow": true,
  "documentation": "https://github.com/mattahr/ha-battaxi",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/mattahr/ha-battaxi/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

- [ ] **Step 4: Write the failing model test**

`tests/test_models.py`:

```python
"""Tests for the internal domain models."""

from datetime import UTC, datetime

from custom_components.stavsnas_battaxi.models import (
    BattaxiDeparture,
    BattaxiRoute,
)

ROUTE_CONFIG = {
    "line_id": "line-1",
    "line_name": "Sandhamnslinjen",
    "origin_id": "pier-a",
    "origin_name": "Stavsnäs",
    "destination_id": "pier-b",
    "destination_name": "Telegrafholmen",
}


def test_route_roundtrips_through_config() -> None:
    route = BattaxiRoute.from_config(ROUTE_CONFIG)
    assert route.as_config() == ROUTE_CONFIG
    assert route.unique_id == "line-1:pier-a:pier-b"
    assert route.title == "Stavsnäs → Telegrafholmen"


def test_departure_is_frozen_and_ordered_by_departure() -> None:
    early = BattaxiDeparture(
        id="1",
        line_id="line-1",
        line_name="Sandhamnslinjen",
        origin_id="pier-a",
        destination_id="pier-b",
        departure=datetime(2026, 9, 12, 14, 0, tzinfo=UTC),
        arrival=datetime(2026, 9, 12, 14, 35, tzinfo=UTC),
        duration_minutes=35,
        available_seats=None,
        bookable=True,
    )
    late = BattaxiDeparture(
        id="2",
        line_id="line-1",
        line_name="Sandhamnslinjen",
        origin_id="pier-a",
        destination_id="pier-b",
        departure=datetime(2026, 9, 12, 17, 0, tzinfo=UTC),
        arrival=datetime(2026, 9, 12, 17, 35, tzinfo=UTC),
        duration_minutes=35,
        available_seats=3,
        bookable=False,
    )
    assert sorted([late, early], key=lambda d: d.departure) == [early, late]
```

- [ ] **Step 5: Write `tests/conftest.py` and `tests/__init__.py`**

```python
"""Shared fixtures for the Stavsnäs Båttaxi tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.stavsnas_battaxi.const import API_BASE_URL, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"

LINE_ID = "6a31a5470bdad9fa1552c80d"  # Sandhamnslinjen
BULLERO_LINE_ID = "6a31a5430bdad9fa1552c74b"
STAVSNAS = "6a31a5430bdad9fa1552c748"
SANDHAMN = "6a31a5470bdad9fa1552c809"
TELEGRAFHOLMEN = "6a31a5470bdad9fa1552c80a"
TROUVILLE = "6a31a5470bdad9fa1552c80b"
LOKHOLMEN = "6a31a5470bdad9fa1552c80c"

ROUTE_DATA = {
    "line_id": LINE_ID,
    "line_name": "Sandhamnslinjen",
    "origin_id": STAVSNAS,
    "origin_name": "Stavsnäs",
    "destination_id": TELEGRAFHOLMEN,
    "destination_name": "Telegrafholmen",
}

PIERS_URL = f"{API_BASE_URL}/api/public/piers"
LINES_URL = f"{API_BASE_URL}/api/public/lines"
SEARCH_URL = f"{API_BASE_URL}/api/search"
SEARCH_URL_RE = re.compile(rf"^{re.escape(SEARCH_URL)}\?.*")


def load_json(name: str) -> Any:
    """Load a JSON fixture from tests/fixtures."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of custom_components in every test."""


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock the reference endpoints and every search with today's departures."""
    aioclient_mock.get(PIERS_URL, json=load_json("piers.json"))
    aioclient_mock.get(LINES_URL, json=load_json("lines.json"))
    aioclient_mock.get(SEARCH_URL_RE, json=load_json("search_with_departures.json"))
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Config entry for Stavsnäs → Telegrafholmen on Sandhamnslinjen."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="test-entry",
        title="Stavsnäs → Telegrafholmen",
        unique_id=f"{LINE_ID}:{STAVSNAS}:{TELEGRAFHOLMEN}",
        data=ROUTE_DATA,
    )
```

`tests/__init__.py` is an empty file. `custom_components/stavsnas_battaxi/__init__.py` starts as:

```python
"""The Stavsnäs Båttaxi integration."""
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.stavsnas_battaxi.models'`

- [ ] **Step 7: Write `models.py`**

```python
"""Domain models for the Stavsnäs Båttaxi integration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .const import (
    CONF_DESTINATION_ID,
    CONF_DESTINATION_NAME,
    CONF_LINE_ID,
    CONF_LINE_NAME,
    CONF_ORIGIN_ID,
    CONF_ORIGIN_NAME,
)


@dataclass(frozen=True, slots=True)
class BattaxiPier:
    """A pier (brygga) that boats can call at."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class BattaxiLine:
    """A line with its ordered stop list (pier ids, includes the return leg)."""

    id: str
    name: str
    stops: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BattaxiRoute:
    """A directed route on a line: origin pier → destination pier."""

    line_id: str
    line_name: str
    origin_id: str
    origin_name: str
    destination_id: str
    destination_name: str

    @property
    def unique_id(self) -> str:
        """Unique id used for the config entry."""
        return f"{self.line_id}:{self.origin_id}:{self.destination_id}"

    @property
    def title(self) -> str:
        """Human readable title: 'Origin → Destination'."""
        return f"{self.origin_name} → {self.destination_name}"

    @classmethod
    def from_config(cls, data: Mapping[str, Any]) -> BattaxiRoute:
        """Build a route from config entry data."""
        return cls(
            line_id=data[CONF_LINE_ID],
            line_name=data[CONF_LINE_NAME],
            origin_id=data[CONF_ORIGIN_ID],
            origin_name=data[CONF_ORIGIN_NAME],
            destination_id=data[CONF_DESTINATION_ID],
            destination_name=data[CONF_DESTINATION_NAME],
        )

    def as_config(self) -> dict[str, str]:
        """Serialize the route as config entry data."""
        return {
            CONF_LINE_ID: self.line_id,
            CONF_LINE_NAME: self.line_name,
            CONF_ORIGIN_ID: self.origin_id,
            CONF_ORIGIN_NAME: self.origin_name,
            CONF_DESTINATION_ID: self.destination_id,
            CONF_DESTINATION_NAME: self.destination_name,
        }


@dataclass(frozen=True, slots=True)
class BattaxiDeparture:
    """A single departure between two piers."""

    id: str
    line_id: str
    line_name: str
    origin_id: str
    destination_id: str
    departure: datetime
    arrival: datetime
    duration_minutes: int | None
    available_seats: int | None
    bookable: bool
```

- [ ] **Step 8: Run tests and ruff**

Run: `uv run pytest tests/test_models.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: 2 passed, ruff clean (run `uv run ruff format .` if formatting differs).

---

### Task 2: API client and JSON parsing

**Files:**
- Create: `custom_components/stavsnas_battaxi/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: models from Task 1, `API_BASE_URL`, `API_TIMEOUT`, `TIMEZONE`.
- Produces: exceptions `BattaxiApiError`, `BattaxiConnectionError(BattaxiApiError)`, `BattaxiRateLimitError(BattaxiApiError)`, `BattaxiInvalidResponseError(BattaxiApiError)`; `BattaxiApi(session, *, base_url=API_BASE_URL, timezone: tzinfo | None = None)` with `.timezone`, `async_get_piers() -> list[BattaxiPier]`, `async_get_lines() -> list[BattaxiLine]`, `async_search(origin_id, destination_id, day: date) -> list[BattaxiDeparture]`; pure parsers `parse_piers(payload)`, `parse_lines(payload)`, `parse_departures(payload, *, origin_id, destination_id, day, tz)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:

```python
"""Tests for the Båttaxi API client and parsers."""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

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
    departures = parse_departures(
        load_json("search_with_departures.json"),
        origin_id=STAVSNAS,
        destination_id=TELEGRAFHOLMEN,
        day=DAY,
        tz=TZ,
    )
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
    departures = parse_departures(
        load_json("search_missing_seats.json"),
        origin_id=STAVSNAS,
        destination_id=TELEGRAFHOLMEN,
        day=DAY,
        tz=TZ,
    )
    assert departures[0].available_seats is None
    assert departures[0].duration_minutes is None


def test_parse_departures_arrival_after_midnight_rolls_over() -> None:
    payload = {
        "items": [
            {
                "departureId": "late",
                "lineId": LINE_ID,
                "lineName": "Sandhamnslinjen",
                "departureTime": "23:50",
                "arrivalTime": "00:20",
                "bookable": True,
            }
        ]
    }
    (departure,) = parse_departures(
        payload, origin_id=STAVSNAS, destination_id=TELEGRAFHOLMEN, day=DAY, tz=TZ
    )
    assert departure.arrival.date() == DAY + timedelta(days=1)
    assert departure.arrival > departure.departure


@pytest.mark.parametrize(
    ("day", "offset"),
    [(date(2026, 1, 10), "+01:00"), (date(2026, 7, 10), "+02:00")],
)
def test_parse_departures_respects_dst(day: date, offset: str) -> None:
    payload = {
        "items": [
            {
                "departureId": "x",
                "lineId": LINE_ID,
                "lineName": "Sandhamnslinjen",
                "departureTime": "10:00",
                "arrivalTime": "10:30",
                "bookable": True,
            }
        ]
    }
    (departure,) = parse_departures(
        payload, origin_id=STAVSNAS, destination_id=TELEGRAFHOLMEN, day=day, tz=TZ
    )
    assert departure.departure.isoformat().endswith(offset)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "items": [
                {
                    "lineId": LINE_ID,
                    "lineName": "x",
                    "departureTime": "10:00",
                    "arrivalTime": "10:30",
                    "bookable": True,
                }
            ]
        },
        {
            "items": [
                {
                    "departureId": "x",
                    "lineId": LINE_ID,
                    "lineName": "x",
                    "departureTime": "10:00",
                    "arrivalTime": "10:30",
                }
            ]
        },
        {
            "items": [
                {
                    "departureId": "x",
                    "lineId": LINE_ID,
                    "lineName": "x",
                    "departureTime": "25:99",
                    "arrivalTime": "10:30",
                    "bookable": True,
                }
            ]
        },
        {"items": "not-a-list"},
        {"no_items": []},
        [],
    ],
)
def test_parse_departures_rejects_bad_schema(payload: object) -> None:
    with pytest.raises(BattaxiInvalidResponseError):
        parse_departures(
            payload, origin_id=STAVSNAS, destination_id=TELEGRAFHOLMEN, day=DAY, tz=TZ
        )


def test_parse_piers_rejects_missing_name() -> None:
    with pytest.raises(BattaxiInvalidResponseError):
        parse_piers({"items": [{"id": "abc"}]})


def test_parse_lines_rejects_missing_stops() -> None:
    with pytest.raises(BattaxiInvalidResponseError):
        parse_lines({"items": [{"id": "abc", "name": "x"}]})


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
        ({"status": 429}, BattaxiRateLimitError),
        ({"status": 500}, BattaxiApiError),
        (
            {
                "status": 400,
                "json": {"error": "querystring/date Required", "statusCode": 400},
            },
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


async def test_client_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    from aiohttp import ClientError

    aioclient_mock.get(PIERS_URL, exc=ClientError("boom"))
    api = BattaxiApi(async_get_clientsession(hass), timezone=TZ)
    with pytest.raises(BattaxiConnectionError):
        await api.async_get_piers()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.stavsnas_battaxi.api'`

- [ ] **Step 3: Write `api.py`**

```python
"""Client for the public Stavsnäs Båttaxi web API."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponseError, ClientSession
from yarl import URL

from .const import API_BASE_URL, API_TIMEOUT, TIMEZONE
from .models import BattaxiDeparture, BattaxiLine, BattaxiPier

_LOGGER = logging.getLogger(__name__)


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
    if not isinstance(item, dict) or key not in item or item[key] is None:
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
```

- [ ] **Step 4: Run tests and ruff**

Run: `uv run pytest tests/test_api.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: all pass. If `aioclient_mock` raises `AssertionError: No mock registered` for the 400 case, keep the `json=` kwarg as written (the mock accepts it together with `status`).

---

### Task 3: Route builder

**Files:**
- Create: `custom_components/stavsnas_battaxi/routes.py`
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `BattaxiLine`, `BattaxiPier`, `BattaxiRoute`.
- Produces: `unique_stops(line) -> list[str]`, `origin_pier_ids(line) -> list[str]`, `destination_pier_ids(line, origin_id) -> list[str]`, `build_route(line, piers_by_id: Mapping[str, BattaxiPier], origin_id, destination_id) -> BattaxiRoute` (raises `ValueError` on unknown pier or invalid pair).

- [ ] **Step 1: Write the failing tests**

`tests/test_routes.py`:

```python
"""Tests for deriving directed routes from a line's ordered stops."""

import pytest

from custom_components.stavsnas_battaxi.api import parse_lines, parse_piers
from custom_components.stavsnas_battaxi.models import BattaxiLine
from custom_components.stavsnas_battaxi.routes import (
    build_route,
    destination_pier_ids,
    origin_pier_ids,
    unique_stops,
)

from .conftest import (
    LINE_ID,
    LOKHOLMEN,
    SANDHAMN,
    STAVSNAS,
    TELEGRAFHOLMEN,
    TROUVILLE,
    load_json,
)


@pytest.fixture
def sandhamn_line() -> BattaxiLine:
    return next(
        line for line in parse_lines(load_json("lines.json")) if line.id == LINE_ID
    )


@pytest.fixture
def piers_by_id() -> dict:
    return {pier.id: pier for pier in parse_piers(load_json("piers.json"))}


def test_unique_stops_preserves_first_appearance_order(
    sandhamn_line: BattaxiLine,
) -> None:
    assert unique_stops(sandhamn_line) == [
        STAVSNAS,
        SANDHAMN,
        TELEGRAFHOLMEN,
        TROUVILLE,
        LOKHOLMEN,
    ]


def test_origins_are_stops_with_a_later_different_stop(
    sandhamn_line: BattaxiLine,
) -> None:
    assert origin_pier_ids(sandhamn_line) == [
        STAVSNAS,
        SANDHAMN,
        TELEGRAFHOLMEN,
        TROUVILLE,
        LOKHOLMEN,
    ]


def test_destinations_after_first_stop(sandhamn_line: BattaxiLine) -> None:
    assert destination_pier_ids(sandhamn_line, STAVSNAS) == [
        SANDHAMN,
        TELEGRAFHOLMEN,
        TROUVILLE,
        LOKHOLMEN,
    ]


def test_destinations_include_return_leg(sandhamn_line: BattaxiLine) -> None:
    # Telegrafholmen appears twice; everything after either occurrence counts,
    # except Telegrafholmen itself.
    assert destination_pier_ids(sandhamn_line, TELEGRAFHOLMEN) == [
        TROUVILLE,
        LOKHOLMEN,
        SANDHAMN,
        STAVSNAS,
    ]
    assert destination_pier_ids(sandhamn_line, LOKHOLMEN) == [
        TELEGRAFHOLMEN,
        SANDHAMN,
        STAVSNAS,
    ]


def test_line_without_routes_has_no_origins() -> None:
    line = BattaxiLine(id="x", name="Enstopp", stops=("a", "a"))
    assert origin_pier_ids(line) == []
    assert destination_pier_ids(line, "a") == []


def test_build_route(sandhamn_line: BattaxiLine, piers_by_id: dict) -> None:
    route = build_route(sandhamn_line, piers_by_id, STAVSNAS, TELEGRAFHOLMEN)
    assert route.line_name == "Sandhamnslinjen"
    assert route.origin_name == "Stavsnäs"
    assert route.destination_name == "Telegrafholmen"
    assert route.unique_id == f"{LINE_ID}:{STAVSNAS}:{TELEGRAFHOLMEN}"


def test_build_route_rejects_invalid_pair(
    sandhamn_line: BattaxiLine, piers_by_id: dict
) -> None:
    with pytest.raises(ValueError):
        build_route(sandhamn_line, piers_by_id, STAVSNAS, STAVSNAS)
    with pytest.raises(ValueError):
        build_route(sandhamn_line, piers_by_id, STAVSNAS, "unknown-pier")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError ... routes`

- [ ] **Step 3: Write `routes.py`**

```python
"""Derive valid directed routes from a line's ordered stop list.

The API lists every stop a boat calls at, in order, including the return leg
(e.g. Stavsnäs → Sandhamn → Telegrafholmen → ... → Sandhamn → Stavsnäs). A
directed route origin → destination is valid when destination appears after
some occurrence of origin. We never assume symmetric traffic.
"""

from __future__ import annotations

from collections.abc import Mapping

from .models import BattaxiLine, BattaxiPier, BattaxiRoute


def unique_stops(line: BattaxiLine) -> list[str]:
    """Return the line's stop ids in order of first appearance, without duplicates."""
    return list(dict.fromkeys(line.stops))


def destination_pier_ids(line: BattaxiLine, origin_id: str) -> list[str]:
    """Return pier ids reachable after boarding at origin_id, in stop order."""
    reachable: dict[str, None] = {}
    seen_origin = False
    for stop in line.stops:
        if stop == origin_id:
            seen_origin = True
        elif seen_origin:
            reachable.setdefault(stop, None)
    return list(reachable)


def origin_pier_ids(line: BattaxiLine) -> list[str]:
    """Return pier ids that have at least one reachable destination."""
    return [stop for stop in unique_stops(line) if destination_pier_ids(line, stop)]


def build_route(
    line: BattaxiLine,
    piers_by_id: Mapping[str, BattaxiPier],
    origin_id: str,
    destination_id: str,
) -> BattaxiRoute:
    """Build a route, validating that the pair is served by the line."""
    if destination_id not in destination_pier_ids(line, origin_id):
        raise ValueError(f"{line.name} does not serve {origin_id} → {destination_id}")
    try:
        origin = piers_by_id[origin_id]
        destination = piers_by_id[destination_id]
    except KeyError as err:
        raise ValueError(f"Unknown pier id {err}") from err
    return BattaxiRoute(
        line_id=line.id,
        line_name=line.name,
        origin_id=origin.id,
        origin_name=origin.name,
        destination_id=destination.id,
        destination_name=destination.name,
    )
```

- [ ] **Step 4: Run tests and ruff**

Run: `uv run pytest tests/test_routes.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: all pass.

---

### Task 4: Formatting helpers for the text sensors

**Files:**
- Create: `custom_components/stavsnas_battaxi/formatting.py`
- Test: `tests/test_formatting.py`

**Interfaces:**
- Consumes: `BattaxiDeparture`, `BattaxiRoute`.
- Produces: `format_clock(dt) -> str` ("HH:MM"), `format_next_departure(departure: BattaxiDeparture | None, route: BattaxiRoute, today: date) -> str | None`, `format_departures_today(departures: Sequence[BattaxiDeparture]) -> str`, `NO_MORE_DEPARTURES_TODAY = "Inga fler avgångar idag"`, `MAX_STATE_LENGTH = 255` truncation with `…`.

- [ ] **Step 1: Write the failing tests**

`tests/test_formatting.py`:

```python
"""Tests for the Swedish display strings."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from custom_components.stavsnas_battaxi.formatting import (
    NO_MORE_DEPARTURES_TODAY,
    format_departures_today,
    format_next_departure,
)
from custom_components.stavsnas_battaxi.models import BattaxiDeparture, BattaxiRoute

from .conftest import ROUTE_DATA

TZ = ZoneInfo("Europe/Stockholm")
ROUTE = BattaxiRoute.from_config(ROUTE_DATA)
TODAY = date(2026, 9, 12)


def departure(
    clock: str,
    *,
    seats: int | None = 42,
    bookable: bool = True,
    day: date = TODAY,
    arrival: str = "18:05",
) -> BattaxiDeparture:
    hour, minute = (int(part) for part in clock.split(":"))
    arr_hour, arr_minute = (int(part) for part in arrival.split(":"))
    return BattaxiDeparture(
        id=f"dep-{clock}",
        line_id=ROUTE.line_id,
        line_name=ROUTE.line_name,
        origin_id=ROUTE.origin_id,
        destination_id=ROUTE.destination_id,
        departure=datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ),
        arrival=datetime(day.year, day.month, day.day, arr_hour, arr_minute, tzinfo=TZ),
        duration_minutes=35,
        available_seats=seats,
        bookable=bookable,
    )


def test_next_departure_with_seats() -> None:
    text = format_next_departure(departure("17:30"), ROUTE, TODAY)
    assert text == "17:30 Stavsnäs → 18:05 Telegrafholmen · 42 lediga"


def test_next_departure_without_seat_info() -> None:
    text = format_next_departure(departure("17:30", seats=None), ROUTE, TODAY)
    assert text == "17:30 Stavsnäs → 18:05 Telegrafholmen"


def test_next_departure_not_bookable() -> None:
    text = format_next_departure(departure("17:30", bookable=False), ROUTE, TODAY)
    assert text == "17:30 Stavsnäs → 18:05 Telegrafholmen · 42 lediga · ej bokningsbar"


def test_next_departure_on_another_day_is_prefixed_with_date() -> None:
    text = format_next_departure(
        departure("10:10", day=date(2026, 9, 13), arrival="10:45"), ROUTE, TODAY
    )
    assert text == "13/9 10:10 Stavsnäs → 10:45 Telegrafholmen · 42 lediga"


def test_next_departure_none() -> None:
    assert format_next_departure(None, ROUTE, TODAY) is None


def test_departures_today_list() -> None:
    text = format_departures_today(
        [
            departure("15:10", seats=12),
            departure("17:10", seats=None),
            departure("19:40", seats=47),
        ]
    )
    assert text == "15:10 – 12 platser | 17:10 | 19:40 – 47 platser"


def test_departures_today_empty() -> None:
    assert format_departures_today([]) == NO_MORE_DEPARTURES_TODAY


def test_departures_today_is_truncated_to_255_chars() -> None:
    many = [
        departure(f"{hour:02d}:{minute:02d}")
        for hour in range(5, 23)
        for minute in (0, 30)
    ]
    text = format_departures_today(many)
    assert len(text) <= 255
    assert text.endswith("…")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: FAIL with `ModuleNotFoundError ... formatting`

- [ ] **Step 3: Write `formatting.py`**

```python
"""Swedish display strings for the convenience text sensors.

These strings are a presentation of the structured sensors, never the source
of truth for automations (see spec §10).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Final

from homeassistant.const import MAX_LENGTH_STATE_STATE

from .models import BattaxiDeparture, BattaxiRoute

NO_MORE_DEPARTURES_TODAY: Final = "Inga fler avgångar idag"
NOT_BOOKABLE: Final = "ej bokningsbar"
SEPARATOR: Final = " · "
LIST_SEPARATOR: Final = " | "
ELLIPSIS: Final = "…"


def format_clock(moment: datetime) -> str:
    """Format a datetime as HH:MM in its own timezone."""
    return moment.strftime("%H:%M")


def _truncate(text: str) -> str:
    """Keep a state string within Home Assistant's 255 character limit."""
    if len(text) <= MAX_LENGTH_STATE_STATE:
        return text
    return text[: MAX_LENGTH_STATE_STATE - len(ELLIPSIS)] + ELLIPSIS


def format_next_departure(
    departure: BattaxiDeparture | None, route: BattaxiRoute, today: date
) -> str | None:
    """'17:30 Stavsnäs → 18:05 Telegrafholmen · 42 lediga' (date-prefixed if not today)."""
    if departure is None:
        return None
    parts = [
        f"{format_clock(departure.departure)} {route.origin_name}"
        f" → {format_clock(departure.arrival)} {route.destination_name}"
    ]
    if departure.available_seats is not None:
        parts.append(f"{departure.available_seats} lediga")
    if not departure.bookable:
        parts.append(NOT_BOOKABLE)
    text = SEPARATOR.join(parts)
    departure_day = departure.departure.date()
    if departure_day != today:
        text = f"{departure_day.day}/{departure_day.month} {text}"
    return _truncate(text)


def format_departures_today(departures: Sequence[BattaxiDeparture]) -> str:
    """'15:10 – 12 platser | 17:10 | 19:40 – 47 platser' or a no-departures text."""
    if not departures:
        return NO_MORE_DEPARTURES_TODAY
    items = []
    for departure in departures:
        item = format_clock(departure.departure)
        if departure.available_seats is not None:
            item += f" – {departure.available_seats} platser"
        items.append(item)
    return _truncate(LIST_SEPARATOR.join(items))
```

- [ ] **Step 4: Run tests and ruff**

Run: `uv run pytest tests/test_formatting.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: all pass.

---

### Task 5: Coordinator with per-date cache and lookahead

**Files:**
- Create: `custom_components/stavsnas_battaxi/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `BattaxiApi` (Task 2), `BattaxiRoute`, `BattaxiDeparture`, constants `UPDATE_INTERVAL`, `FUTURE_CACHE_TTL`, `MAX_LOOKAHEAD_DAYS`, `DOMAIN`.
- Produces: `type BattaxiConfigEntry = ConfigEntry[BattaxiCoordinator]`; `BattaxiData(today: date, now: datetime, departures_today: list[BattaxiDeparture], next_departure: BattaxiDeparture | None)`; `BattaxiCoordinator(hass, entry, api, route)` with attributes `.entry`, `.route`, `.api`, method `cache_summary() -> list[dict[str, Any]]` (for diagnostics) and `data: BattaxiData`.

- [ ] **Step 1: Write the failing tests**

`tests/test_coordinator.py`:

```python
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
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

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
    assert coordinator.data.next_departure.departure.date().isoformat() == "2026-09-13"

    freezer.move_to("2026-09-13 01:00:00+02:00")
    await coordinator.async_refresh()

    # 2026-09-13 is now "today" and is always re-fetched, not served from cache.
    assert coordinator.data.today.isoformat() == "2026-09-13"
    assert [d.id for d in coordinator.data.departures_today] == [
        "6a75c74b29f5bc095722dc99"
    ]
    assert [entry["date"] for entry in coordinator.cache_summary()] == []


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
        await coordinator._async_update_data()  # noqa: SLF001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coordinator.py -v`
Expected: FAIL with `ModuleNotFoundError ... coordinator`

- [ ] **Step 3: Write `coordinator.py`**

```python
"""DataUpdateCoordinator for one configured Båttaxi route."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BattaxiApi, BattaxiApiError, BattaxiRateLimitError
from .const import DOMAIN, FUTURE_CACHE_TTL, MAX_LOOKAHEAD_DAYS, UPDATE_INTERVAL
from .models import BattaxiDeparture, BattaxiRoute

_LOGGER = logging.getLogger(__name__)

type BattaxiConfigEntry = ConfigEntry[BattaxiCoordinator]


@dataclass(slots=True)
class BattaxiData:
    """Coordinator data for one route."""

    today: date
    now: datetime
    departures_today: list[BattaxiDeparture]
    next_departure: BattaxiDeparture | None


@dataclass(slots=True)
class _CachedDay:
    fetched_at: datetime
    departures: list[BattaxiDeparture] = field(default_factory=list)


class BattaxiCoordinator(DataUpdateCoordinator[BattaxiData]):
    """Fetch departures for a route, caching future dates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BattaxiConfigEntry,
        api: BattaxiApi,
        route: BattaxiRoute,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {route.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self.api = api
        self.route = route
        self._cache: dict[date, _CachedDay] = {}

    def cache_summary(self) -> list[dict[str, Any]]:
        """Describe cached future dates (used by diagnostics)."""
        return [
            {
                "date": day.isoformat(),
                "fetched_at": cached.fetched_at.isoformat(),
                "departures": len(cached.departures),
            }
            for day, cached in sorted(self._cache.items())
        ]

    async def _async_update_data(self) -> BattaxiData:
        now = dt_util.now(self.api.timezone)
        today = now.date()
        self._purge_cache(today)

        try:
            departures_today = [
                departure
                for departure in await self._async_fetch_day(today)
                if departure.departure >= now
            ]
            next_departure = departures_today[0] if departures_today else None
            if next_departure is None:
                next_departure = await self._async_find_next_departure(today, now)
        except BattaxiRateLimitError as err:
            raise UpdateFailed("Båttaxi API rate limit hit, will retry later") from err
        except BattaxiApiError as err:
            raise UpdateFailed(f"Error fetching departures: {err}") from err

        if next_departure is not None:
            _LOGGER.debug(
                "Selected next departure at %s", next_departure.departure.isoformat()
            )
        return BattaxiData(
            today=today,
            now=now,
            departures_today=departures_today,
            next_departure=next_departure,
        )

    async def _async_find_next_departure(
        self, today: date, now: datetime
    ) -> BattaxiDeparture | None:
        """Look ahead day by day (cached) until a day with traffic is found."""
        for offset in range(1, MAX_LOOKAHEAD_DAYS + 1):
            day = today + timedelta(days=offset)
            departures = await self._async_cached_day(day, now)
            if departures:
                return departures[0]
        _LOGGER.debug("No departures within %d days", MAX_LOOKAHEAD_DAYS)
        return None

    async def _async_cached_day(
        self, day: date, now: datetime
    ) -> list[BattaxiDeparture]:
        cached = self._cache.get(day)
        if cached is not None and now - cached.fetched_at < FUTURE_CACHE_TTL:
            _LOGGER.debug("Using cached result for %s", day)
            return cached.departures
        departures = await self._async_fetch_day(day)
        self._cache[day] = _CachedDay(fetched_at=now, departures=departures)
        return departures

    async def _async_fetch_day(self, day: date) -> list[BattaxiDeparture]:
        """Fetch one day, keep only the configured line, sorted by departure."""
        departures = await self.api.async_search(
            self.route.origin_id, self.route.destination_id, day
        )
        selected = sorted(
            (d for d in departures if d.line_id == self.route.line_id),
            key=lambda d: d.departure,
        )
        _LOGGER.debug("Fetched %d departures for %s", len(selected), day)
        return selected

    def _purge_cache(self, today: date) -> None:
        for day in [day for day in self._cache if day <= today]:
            del self._cache[day]
```

- [ ] **Step 4: Run tests and ruff**

Run: `uv run pytest tests/test_coordinator.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: all pass. If `freezer.tick` does not affect `dt_util.now`, check that the test uses `freezer` (pytest-freezer) — it patches `datetime.now` globally.

---

### Task 6: Integration setup, base entity, sensors and binary sensor

**Files:**
- Modify: `custom_components/stavsnas_battaxi/__init__.py` (replace placeholder)
- Create: `custom_components/stavsnas_battaxi/entity.py`
- Create: `custom_components/stavsnas_battaxi/sensor.py`
- Create: `custom_components/stavsnas_battaxi/binary_sensor.py`
- Create: `custom_components/stavsnas_battaxi/icons.json`
- Create: `custom_components/stavsnas_battaxi/strings.json`, `translations/en.json`, `translations/sv.json` (entity section now; config section is completed in Task 7 – write the full files here so Task 7 only has to verify them)
- Test: `tests/test_init.py`, `tests/test_sensor.py`

**Interfaces:**
- Consumes: `BattaxiCoordinator`, `BattaxiData`, `BattaxiConfigEntry`, `BattaxiApi`, `BattaxiRoute`, formatting helpers.
- Produces: `async_setup_entry`, `async_unload_entry`; `BattaxiEntity(coordinator, description: EntityDescription)`; sensor keys `next_departure`, `next_departure_text`, `next_arrival`, `available_seats`, `departures_today`, `departures_today_text`; binary sensor key `bookable`. Entity unique_id `f"{entry.entry_id}_{key}"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_init.py`:

```python
"""Tests for config entry setup and unload."""

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import SEARCH_URL


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-09-12 17:00:00+02:00")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data.data.next_departure is not None

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_api_is_down(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(SEARCH_URL, status=500)
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
```

`tests/test_sensor.py`:

```python
"""Tests for the sensor and binary sensor entities."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

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
```

Note: timestamp sensor states are rendered by HA in UTC (`17:10:00+00:00` == 19:10 Stockholm).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_init.py tests/test_sensor.py -v`
Expected: FAIL (setup returns False / entities missing – `async_setup_entry` does not exist yet).

- [ ] **Step 3: Write `__init__.py`**

```python
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
        async_get_clientsession(hass), timezone=dt_util.get_time_zone(TIMEZONE)
    )
    coordinator = BattaxiCoordinator(hass, entry, api, route)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BattaxiConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 4: Write `entity.py`**

```python
"""Base entity for the Stavsnäs Båttaxi integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONFIGURATION_URL, DOMAIN, MANUFACTURER
from .coordinator import BattaxiCoordinator, BattaxiData
from .models import BattaxiRoute


class BattaxiEntity(CoordinatorEntity[BattaxiCoordinator]):
    """Entity belonging to one route's service device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: BattaxiCoordinator, description: EntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.entry.entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=coordinator.route.title,
            manufacturer=MANUFACTURER,
            model=coordinator.route.line_name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CONFIGURATION_URL,
        )

    @property
    def route(self) -> BattaxiRoute:
        """The configured route."""
        return self.coordinator.route

    @property
    def data(self) -> BattaxiData:
        """Latest coordinator data."""
        return self.coordinator.data
```

- [ ] **Step 5: Write `sensor.py`**

```python
"""Sensors for the Stavsnäs Båttaxi integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BattaxiConfigEntry, BattaxiData
from .entity import BattaxiEntity
from .formatting import format_clock, format_departures_today, format_next_departure
from .models import BattaxiRoute

type SensorValue = datetime | int | str | None


@dataclass(frozen=True, kw_only=True)
class BattaxiSensorEntityDescription(SensorEntityDescription):
    """Describes a Båttaxi sensor."""

    value_fn: Callable[[BattaxiData, BattaxiRoute], SensorValue]
    attributes_fn: Callable[[BattaxiData, BattaxiRoute], dict[str, Any]] | None = None


def _next_departure_attributes(
    data: BattaxiData, route: BattaxiRoute
) -> dict[str, Any]:
    if data.next_departure is None:
        return {}
    return {
        "line": route.line_name,
        "origin": route.origin_name,
        "destination": route.destination_name,
        "departure_id": data.next_departure.id,
    }


def _departures_today_attributes(
    data: BattaxiData, route: BattaxiRoute
) -> dict[str, Any]:
    return {
        "departures": [
            {
                "departure": format_clock(departure.departure),
                "arrival": format_clock(departure.arrival),
                "available_seats": departure.available_seats,
                "bookable": departure.bookable,
            }
            for departure in data.departures_today
        ]
    }


SENSORS: tuple[BattaxiSensorEntityDescription, ...] = (
    BattaxiSensorEntityDescription(
        key="next_departure",
        translation_key="next_departure",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, _: (
            data.next_departure.departure if data.next_departure else None
        ),
        attributes_fn=_next_departure_attributes,
    ),
    BattaxiSensorEntityDescription(
        key="next_departure_text",
        translation_key="next_departure_text",
        value_fn=lambda data, route: format_next_departure(
            data.next_departure, route, data.today
        ),
    ),
    BattaxiSensorEntityDescription(
        key="next_arrival",
        translation_key="next_arrival",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data, _: (
            data.next_departure.arrival if data.next_departure else None
        ),
    ),
    BattaxiSensorEntityDescription(
        key="available_seats",
        translation_key="available_seats",
        value_fn=lambda data, _: (
            data.next_departure.available_seats if data.next_departure else None
        ),
    ),
    BattaxiSensorEntityDescription(
        key="departures_today",
        translation_key="departures_today",
        value_fn=lambda data, _: len(data.departures_today),
        attributes_fn=_departures_today_attributes,
    ),
    BattaxiSensorEntityDescription(
        key="departures_today_text",
        translation_key="departures_today_text",
        value_fn=lambda data, _: format_departures_today(data.departures_today),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BattaxiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors for a route."""
    coordinator = entry.runtime_data
    async_add_entities(
        BattaxiSensor(coordinator, description) for description in SENSORS
    )


class BattaxiSensor(BattaxiEntity, SensorEntity):
    """A sensor reading one value from the coordinator data."""

    entity_description: BattaxiSensorEntityDescription

    @property
    def native_value(self) -> SensorValue:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.data, self.route)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes when the description defines them."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.data, self.route)
```

- [ ] **Step 6: Write `binary_sensor.py`**

```python
"""Binary sensors for the Stavsnäs Båttaxi integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BattaxiConfigEntry
from .entity import BattaxiEntity

BOOKABLE = BinarySensorEntityDescription(key="bookable", translation_key="bookable")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BattaxiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors for a route."""
    async_add_entities([BattaxiBookableSensor(entry.runtime_data, BOOKABLE)])


class BattaxiBookableSensor(BattaxiEntity, BinarySensorEntity):
    """Whether Båttaxi reports the next departure as bookable.

    'off' only means the API does not offer booking right now (e.g. full or
    too close to departure). It never means the departure is cancelled.
    """

    @property
    def is_on(self) -> bool | None:
        """Return True when the next departure is bookable, None without a departure."""
        if self.data.next_departure is None:
            return None
        return self.data.next_departure.bookable
```

- [ ] **Step 7: Write `icons.json`, `strings.json` and translations**

`icons.json`:

```json
{
  "entity": {
    "binary_sensor": {
      "bookable": {"default": "mdi:ticket-confirmation-outline", "state": {"on": "mdi:ticket-confirmation"}}
    },
    "sensor": {
      "next_departure_text": {"default": "mdi:ferry"},
      "available_seats": {"default": "mdi:seat-passenger"},
      "departures_today": {"default": "mdi:ferry"},
      "departures_today_text": {"default": "mdi:ferry"}
    }
  }
}
```

`strings.json` (identical content in `translations/en.json`):

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Stavsnäs Båttaxi",
        "description": "Select the line you want to follow. Lines and piers are fetched from Båttaxi's booking API.",
        "data": {"line": "Line"}
      },
      "reconfigure": {
        "title": "Stavsnäs Båttaxi",
        "description": "Select the line you want to follow. Lines and piers are fetched from Båttaxi's booking API.",
        "data": {"line": "Line"}
      },
      "origin": {
        "title": "From pier",
        "description": "Line: {line}",
        "data": {"origin": "From pier"}
      },
      "destination": {
        "title": "To pier",
        "description": "Line: {line}\nFrom: {origin}",
        "data": {"destination": "To pier"}
      }
    },
    "error": {
      "cannot_connect": "Could not reach Båttaxi's API. Try again later.",
      "invalid_route": "That pier is not served after the selected departure pier."
    },
    "abort": {
      "already_configured": "This route is already configured.",
      "cannot_connect": "Could not fetch lines and piers from Båttaxi's API. Try again later.",
      "no_lines": "Båttaxi's API returned no lines with routes.",
      "reconfigure_successful": "The route was updated."
    }
  },
  "entity": {
    "binary_sensor": {
      "bookable": {"name": "Bookable"}
    },
    "sensor": {
      "next_departure": {"name": "Next departure"},
      "next_departure_text": {"name": "Next departure text"},
      "next_arrival": {"name": "Next arrival"},
      "available_seats": {"name": "Available seats"},
      "departures_today": {"name": "Departures today"},
      "departures_today_text": {"name": "Departures today text"}
    }
  }
}
```

`translations/sv.json`:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Stavsnäs Båttaxi",
        "description": "Välj den linje du vill följa. Linjer och bryggor hämtas från Båttaxis boknings-API.",
        "data": {"line": "Linje"}
      },
      "reconfigure": {
        "title": "Stavsnäs Båttaxi",
        "description": "Välj den linje du vill följa. Linjer och bryggor hämtas från Båttaxis boknings-API.",
        "data": {"line": "Linje"}
      },
      "origin": {
        "title": "Från brygga",
        "description": "Linje: {line}",
        "data": {"origin": "Från brygga"}
      },
      "destination": {
        "title": "Till brygga",
        "description": "Linje: {line}\nFrån: {origin}",
        "data": {"destination": "Till brygga"}
      }
    },
    "error": {
      "cannot_connect": "Kunde inte nå Båttaxis API. Försök igen senare.",
      "invalid_route": "Den bryggan trafikeras inte efter vald avgångsbrygga."
    },
    "abort": {
      "already_configured": "Den här sträckan är redan konfigurerad.",
      "cannot_connect": "Kunde inte hämta linjer och bryggor från Båttaxis API. Försök igen senare.",
      "no_lines": "Båttaxis API returnerade inga linjer med sträckor.",
      "reconfigure_successful": "Sträckan uppdaterades."
    }
  },
  "entity": {
    "binary_sensor": {
      "bookable": {"name": "Bokningsbar"}
    },
    "sensor": {
      "next_departure": {"name": "Nästa avgång"},
      "next_departure_text": {"name": "Nästa avgång text"},
      "next_arrival": {"name": "Nästa ankomst"},
      "available_seats": {"name": "Lediga platser"},
      "departures_today": {"name": "Avgångar idag"},
      "departures_today_text": {"name": "Avgångar idag text"}
    }
  }
}
```

- [ ] **Step 8: Run tests and ruff**

Run: `uv run pytest tests/test_init.py tests/test_sensor.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: all pass. If the `friendly_name` assertion fails because translations are not loaded, make sure `translations/en.json` exists and the entity descriptions carry `translation_key`.

---

### Task 7: Config flow (user + reconfigure)

**Files:**
- Create: `custom_components/stavsnas_battaxi/config_flow.py`
- Verify: `strings.json`, `translations/en.json`, `translations/sv.json` (written in Task 6) contain every step/error/abort key used here.
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `BattaxiApi`, `BattaxiApiError`, `origin_pier_ids`, `destination_pier_ids`, `build_route`, `CONF_LINE`, `CONF_ORIGIN`, `CONF_DESTINATION`, `BattaxiRoute.unique_id/.title/.as_config()`.
- Produces: `BattaxiConfigFlow` with steps `user` → `origin` → `destination`, and `reconfigure` → `origin` → `destination`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config_flow.py`:

```python
"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.stavsnas_battaxi.const import (
    CONF_DESTINATION,
    CONF_LINE,
    CONF_ORIGIN,
    DOMAIN,
)

from .conftest import (
    LINE_ID,
    LINES_URL,
    LOKHOLMEN,
    PIERS_URL,
    ROUTE_DATA,
    SANDHAMN,
    SEARCH_URL,
    STAVSNAS,
    TELEGRAFHOLMEN,
    TROUVILLE,
    load_json,
)


@pytest.fixture
def mock_setup_entry() -> AsyncMock:
    with patch(
        "custom_components.stavsnas_battaxi.async_setup_entry", return_value=True
    ) as mock:
        yield mock


def option_values(result: dict, field: str) -> list[str]:
    """Return the option values of a SelectSelector field in a form result."""
    schema = result["data_schema"].schema
    selector = next(value for key, value in schema.items() if key == field)
    return [option["value"] for option in selector.config["options"]]


async def test_full_user_flow(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, mock_setup_entry: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert LINE_ID in option_values(result, CONF_LINE)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LINE: LINE_ID}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "origin"
    assert option_values(result, CONF_ORIGIN) == [
        STAVSNAS,
        SANDHAMN,
        TELEGRAFHOLMEN,
        TROUVILLE,
        LOKHOLMEN,
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORIGIN: STAVSNAS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "destination"
    assert option_values(result, CONF_DESTINATION) == [
        SANDHAMN,
        TELEGRAFHOLMEN,
        TROUVILLE,
        LOKHOLMEN,
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DESTINATION: TELEGRAFHOLMEN}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Stavsnäs → Telegrafholmen"
    assert result["data"] == ROUTE_DATA
    assert result["result"].unique_id == f"{LINE_ID}:{STAVSNAS}:{TELEGRAFHOLMEN}"
    assert mock_setup_entry.call_count == 1


async def test_api_down_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(PIERS_URL, status=500)
    aioclient_mock.get(LINES_URL, json=load_json("lines.json"))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_no_lines_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(PIERS_URL, json=load_json("piers.json"))
    aioclient_mock.get(LINES_URL, json={"items": []})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_lines"


async def test_duplicate_route_aborts(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LINE: LINE_ID}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORIGIN: STAVSNAS}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DESTINATION: TELEGRAFHOLMEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_search_error_shows_error_then_recovers(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_setup_entry: AsyncMock,
) -> None:
    aioclient_mock.get(PIERS_URL, json=load_json("piers.json"))
    aioclient_mock.get(LINES_URL, json=load_json("lines.json"))
    aioclient_mock.get(SEARCH_URL, exc=TimeoutError())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LINE: LINE_ID}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORIGIN: STAVSNAS}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DESTINATION: TELEGRAFHOLMEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "destination"
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(SEARCH_URL, json=load_json("search_empty.json"))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DESTINATION: TELEGRAFHOLMEN}
    )
    # Zero departures today is a valid configuration.
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reconfigure_changes_route(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LINE: LINE_ID}
    )
    assert result["step_id"] == "origin"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORIGIN: STAVSNAS}
    )
    assert result["step_id"] == "destination"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DESTINATION: SANDHAMN}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.unique_id == f"{LINE_ID}:{STAVSNAS}:{SANDHAMN}"
    assert config_entry.title == "Stavsnäs → Sandhamn"
    assert config_entry.data["destination_name"] == "Sandhamn"


async def test_reconfigure_to_existing_route_aborts(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    other = MockConfigEntry(
        domain=DOMAIN,
        entry_id="other-entry",
        title="Stavsnäs → Sandhamn",
        unique_id=f"{LINE_ID}:{STAVSNAS}:{SANDHAMN}",
        data={**ROUTE_DATA, "destination_id": SANDHAMN, "destination_name": "Sandhamn"},
    )
    other.add_to_hass(hass)
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LINE: LINE_ID}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORIGIN: STAVSNAS}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DESTINATION: SANDHAMN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_flow.py -v`
Expected: FAIL (`UnknownHandler` – no config flow registered).

- [ ] **Step 3: Write `config_flow.py`**

```python
"""Config flow for Stavsnäs Båttaxi: line → from pier → to pier."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util

from .api import BattaxiApi, BattaxiApiError
from .const import CONF_DESTINATION, CONF_LINE, CONF_ORIGIN, DOMAIN, TIMEZONE
from .models import BattaxiLine, BattaxiPier, BattaxiRoute
from .routes import build_route, destination_pier_ids, origin_pier_ids

_LOGGER = logging.getLogger(__name__)


def _select(field: str, options: list[SelectOptionDict]) -> vol.Schema:
    """Build a one-field form schema with a searchable dropdown."""
    return vol.Schema(
        {
            vol.Required(field): SelectSelector(
                SelectSelectorConfig(
                    options=options, mode=SelectSelectorMode.DROPDOWN, sort=False
                )
            )
        }
    )


class BattaxiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._api: BattaxiApi | None = None
        self._lines: dict[str, BattaxiLine] = {}
        self._piers: dict[str, BattaxiPier] = {}
        self._line: BattaxiLine | None = None
        self._origin_id: str | None = None

    @property
    def api(self) -> BattaxiApi:
        """Lazily create the API client."""
        if self._api is None:
            self._api = BattaxiApi(
                async_get_clientsession(self.hass),
                timezone=dt_util.get_time_zone(TIMEZONE),
            )
        return self._api

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: pick a line."""
        return await self._async_step_line("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure: pick a (possibly different) line."""
        return await self._async_step_line("reconfigure", user_input)

    async def _async_step_line(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if not self._lines:
            try:
                piers, lines = await asyncio.gather(
                    self.api.async_get_piers(), self.api.async_get_lines()
                )
            except BattaxiApiError as err:
                _LOGGER.warning("Could not fetch Båttaxi reference data: %s", err)
                return self.async_abort(reason="cannot_connect")
            self._piers = {pier.id: pier for pier in piers}
            self._lines = {line.id: line for line in lines if origin_pier_ids(line)}
            if not self._lines:
                return self.async_abort(reason="no_lines")

        if user_input is not None:
            self._line = self._lines[user_input[CONF_LINE]]
            return await self.async_step_origin()

        options = [
            SelectOptionDict(value=line.id, label=line.name)
            for line in self._lines.values()
        ]
        return self.async_show_form(
            step_id=step_id, data_schema=_select(CONF_LINE, options)
        )

    async def async_step_origin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step: pick the departure pier."""
        assert self._line is not None
        if user_input is not None:
            self._origin_id = user_input[CONF_ORIGIN]
            return await self.async_step_destination()

        return self.async_show_form(
            step_id="origin",
            data_schema=_select(
                CONF_ORIGIN, self._pier_options(origin_pier_ids(self._line))
            ),
            description_placeholders={"line": self._line.name},
        )

    async def async_step_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Third step: pick the arrival pier, verify the API and finish."""
        assert self._line is not None
        assert self._origin_id is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                route = build_route(
                    self._line,
                    self._piers,
                    self._origin_id,
                    user_input[CONF_DESTINATION],
                )
            except ValueError:
                errors["base"] = "invalid_route"
            else:
                try:
                    # Zero departures is fine; we only verify the API accepts the ids.
                    await self.api.async_search(
                        route.origin_id,
                        route.destination_id,
                        dt_util.now(self.api.timezone).date(),
                    )
                except BattaxiApiError as err:
                    _LOGGER.warning("Could not verify route with Båttaxi API: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    return await self._async_finish(route)

        return self.async_show_form(
            step_id="destination",
            data_schema=_select(
                CONF_DESTINATION,
                self._pier_options(destination_pier_ids(self._line, self._origin_id)),
            ),
            errors=errors,
            description_placeholders={
                "line": self._line.name,
                "origin": self._piers[self._origin_id].name
                if self._origin_id in self._piers
                else self._origin_id,
            },
        )

    async def _async_finish(self, route: BattaxiRoute) -> ConfigFlowResult:
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if route.unique_id != entry.unique_id:
                await self.async_set_unique_id(route.unique_id)
                self._abort_if_unique_id_configured()
            return self.async_update_reload_and_abort(
                entry,
                unique_id=route.unique_id,
                title=route.title,
                data=route.as_config(),
            )

        await self.async_set_unique_id(route.unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=route.title, data=route.as_config())

    def _pier_options(self, pier_ids: list[str]) -> list[SelectOptionDict]:
        return [
            SelectOptionDict(value=pier_id, label=self._piers[pier_id].name)
            for pier_id in pier_ids
            if pier_id in self._piers
        ]
```

- [ ] **Step 4: Run tests and ruff**

Run: `uv run pytest tests/test_config_flow.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: all pass. If `option_values` fails to find the selector, inspect `result["data_schema"].schema` keys – they are `vol.Required` markers that compare equal to the field name string.

---

### Task 8: Diagnostics

**Files:**
- Create: `custom_components/stavsnas_battaxi/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `BattaxiConfigEntry`, `BattaxiCoordinator.cache_summary()`, `BattaxiData`.
- Produces: `async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing test**

`tests/test_diagnostics.py`:

```python
"""Tests for config entry diagnostics."""

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

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
    assert diagnostics["today"] == "2026-09-12"
    assert diagnostics["departures_today"] == 1
    assert diagnostics["next_departure"]["departure"] == "2026-09-12T19:10:00+02:00"
    assert diagnostics["next_departure"]["bookable"] is True
    assert diagnostics["cached_dates"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_diagnostics.py -v`
Expected: FAIL with `ModuleNotFoundError ... diagnostics`

- [ ] **Step 3: Write `diagnostics.py`**

```python
"""Diagnostics support for Stavsnäs Båttaxi."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import BattaxiConfigEntry
from .models import BattaxiDeparture


def _departure_summary(departure: BattaxiDeparture | None) -> dict[str, Any] | None:
    if departure is None:
        return None
    return {
        "id": departure.id,
        "line_id": departure.line_id,
        "departure": departure.departure.isoformat(),
        "arrival": departure.arrival.isoformat(),
        "available_seats": departure.available_seats,
        "bookable": departure.bookable,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BattaxiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (no credentials exist to redact)."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "route": dict(entry.data),
        "last_update_success": coordinator.last_update_success,
        "last_update": data.now.isoformat() if data else None,
        "today": data.today.isoformat() if data else None,
        "departures_today": len(data.departures_today) if data else None,
        "next_departure": _departure_summary(data.next_departure) if data else None,
        "cached_dates": coordinator.cache_summary(),
    }
```

- [ ] **Step 4: Run the full suite and ruff**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: all tests pass, ruff clean.

---

### Task 9: Docker dev environment and F5 debugging

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `dev/ha.sh` (executable), `dev/config/configuration.yaml`
- Create: `.vscode/launch.json`, `.vscode/tasks.json`, `.vscode/settings.json`, `.vscode/extensions.json`
- Create: `.gitignore`

**Interfaces:**
- Produces: `./dev/ha.sh up|down|restart|logs|status`. `up` refuses to start when `HA_PORT`/`DEBUGPY_PORT` are held by anything other than our own container and prints what holds them; it then waits until debugpy accepts connections. F5 runs task `ha: up` and attaches.

- [ ] **Step 1: Write `docker-compose.yml` and `.env.example`**

`docker-compose.yml`:

```yaml
name: ha-battaxi

services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: ha-battaxi
    ports:
      - "${HA_PORT:-8123}:8123"
      - "${DEBUGPY_PORT:-5678}:5678"
    volumes:
      - ./dev/config:/config
      - ./custom_components:/config/custom_components
      - /etc/localtime:/etc/localtime:ro
    environment:
      - TZ=Europe/Stockholm
      - PYTHONDONTWRITEBYTECODE=1
    restart: unless-stopped
```

`.env.example`:

```dotenv
# Copy to .env to override the host ports used by `dev/ha.sh` / F5.
HA_PORT=8123
DEBUGPY_PORT=5678
```

- [ ] **Step 2: Write `dev/config/configuration.yaml`**

```yaml
# Minimal Home Assistant configuration for developing the integration.
default_config:

# Lets VS Code attach on port 5678 (see .vscode/launch.json).
debugpy:
  start: true
  wait: false

logger:
  default: warning
  logs:
    custom_components.stavsnas_battaxi: debug
```

- [ ] **Step 3: Write `dev/ha.sh`**

```bash
#!/usr/bin/env bash
# Start/stop the Home Assistant dev container and check that its ports are free.
#
#   dev/ha.sh up       start (refuses if HA_PORT/DEBUGPY_PORT are taken by something else)
#   dev/ha.sh down     stop and remove the container
#   dev/ha.sh restart  restart Home Assistant (needed after code changes)
#   dev/ha.sh logs     follow the Home Assistant log
#   dev/ha.sh status   show container state and who holds the ports
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi
HA_PORT="${HA_PORT:-8123}"
DEBUGPY_PORT="${DEBUGPY_PORT:-5678}"
CONTAINER="ha-battaxi"

own_container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)" = "true" ]
}

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

describe_port_holder() {
  local port="$1" container
  container="$(docker ps --filter "publish=$port" --format '{{.Names}} ({{.Image}})' 2>/dev/null | head -n1)"
  if [ -n "$container" ]; then
    echo "Docker container $container"
  else
    lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR==2 {print $1 " (pid " $2 ")"}'
  fi
}

check_ports_free() {
  local busy=0 port
  for port in "$HA_PORT" "$DEBUGPY_PORT"; do
    if port_in_use "$port"; then
      echo "✖ Port $port is already in use by: $(describe_port_holder "$port")" >&2
      busy=1
    fi
  done
  if [ "$busy" -ne 0 ]; then
    echo "  Stop it (e.g. 'docker stop <name>') or set HA_PORT/DEBUGPY_PORT in .env" >&2
    exit 1
  fi
}

wait_for_debugpy() {
  local timeout="${1:-180}" waited=0
  printf 'Waiting for debugpy on localhost:%s ' "$DEBUGPY_PORT"
  until nc -z localhost "$DEBUGPY_PORT" >/dev/null 2>&1; do
    if ! own_container_running; then
      echo; echo "✖ Container $CONTAINER stopped unexpectedly. Logs:" >&2
      docker logs --tail 50 "$CONTAINER" >&2 || true
      exit 1
    fi
    if [ "$waited" -ge "$timeout" ]; then
      echo; echo "✖ debugpy did not come up within ${timeout}s. See: dev/ha.sh logs" >&2
      exit 1
    fi
    sleep 2; waited=$((waited + 2)); printf '.'
  done
  echo " ready"
  echo "✔ Home Assistant: http://localhost:$HA_PORT  (debugpy on $DEBUGPY_PORT)"
}

case "${1:-}" in
  up)
    if own_container_running; then
      echo "✔ $CONTAINER is already running"
    else
      check_ports_free
      docker compose up -d
    fi
    wait_for_debugpy
    ;;
  down)
    docker compose down
    ;;
  restart)
    docker compose restart
    wait_for_debugpy
    ;;
  logs)
    docker compose logs -f --tail 200
    ;;
  status)
    docker compose ps
    for port in "$HA_PORT" "$DEBUGPY_PORT"; do
      if port_in_use "$port"; then
        echo "port $port: $(describe_port_holder "$port")"
      else
        echo "port $port: free"
      fi
    done
    ;;
  *)
    sed -n '2,9p' "$0"
    exit 2
    ;;
esac
```

Run: `chmod +x dev/ha.sh`

- [ ] **Step 4: Write the VS Code files**

`.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Home Assistant (Docker): attach",
      "type": "debugpy",
      "request": "attach",
      "connect": {"host": "localhost", "port": 5678},
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/custom_components",
          "remoteRoot": "/config/custom_components"
        }
      ],
      "justMyCode": true,
      "preLaunchTask": "ha: up"
    },
    {
      "name": "pytest: current file",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": ["${file}", "-v"],
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ]
}
```

`.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "ha: up",
      "type": "shell",
      "command": "./dev/ha.sh up",
      "problemMatcher": [],
      "presentation": {"reveal": "always", "panel": "shared", "clear": true}
    },
    {
      "label": "ha: down",
      "type": "shell",
      "command": "./dev/ha.sh down",
      "problemMatcher": []
    },
    {
      "label": "ha: restart",
      "type": "shell",
      "command": "./dev/ha.sh restart",
      "problemMatcher": []
    },
    {
      "label": "ha: logs",
      "type": "shell",
      "command": "./dev/ha.sh logs",
      "isBackground": true,
      "problemMatcher": []
    },
    {
      "label": "ha: status",
      "type": "shell",
      "command": "./dev/ha.sh status",
      "problemMatcher": []
    },
    {
      "label": "test",
      "type": "shell",
      "command": "uv run pytest",
      "group": {"kind": "test", "isDefault": true},
      "problemMatcher": []
    }
  ]
}
```

`.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true
  },
  "files.exclude": {"**/__pycache__": true}
}
```

`.vscode/extensions.json`:

```json
{
  "recommendations": ["ms-python.python", "ms-python.debugpy", "charliermarsh.ruff"]
}
```

- [ ] **Step 5: Write `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.env

# Home Assistant dev config: keep only configuration.yaml
dev/config/*
!dev/config/configuration.yaml
```

- [ ] **Step 6: Verify the port check and the F5 path manually**

Run: `./dev/ha.sh status` → shows `port 8123: free` (or who holds it).
Run: `./dev/ha.sh up` → prints "Waiting for debugpy ... ready" and the URL. Then `./dev/ha.sh status` shows the container running.
Run: `python3 -m http.server 5678 &` then `./dev/ha.sh down && ./dev/ha.sh up` → must print `✖ Port 5678 is already in use by: Python (pid ...)` and exit 1. Kill the http server afterwards.
Run: `docker exec ha-battaxi ls /config/custom_components/stavsnas_battaxi/manifest.json` → file exists inside the container.
Run: `docker logs ha-battaxi 2>&1 | grep -i "stavsnas_battaxi\|custom integration"` → HA logged the custom integration warning (proof it was loaded).
Finally `./dev/ha.sh down`.

---

### Task 10: HACS packaging, README, license, CI and documentation update

**Files:**
- Create: `hacs.json`, `LICENSE`, `README.md`, `.github/workflows/validate.yml`, `.github/workflows/tests.yml`
- Modify: `docs/stavsnas_battaxi_home_assistant_design.md` (status line + §31 dev-env notes if anything changed during implementation)

- [ ] **Step 1: Write `hacs.json`**

```json
{
  "name": "Stavsnäs Båttaxi",
  "render_readme": true,
  "homeassistant": "2026.9.0"
}
```

- [ ] **Step 2: Write `LICENSE` (MIT, copyright 2026 Mattias Ahrens)**

Standard MIT text with `Copyright (c) 2026 Mattias Ahrens`.

- [ ] **Step 3: Write `.github/workflows/validate.yml` and `tests.yml`**

`validate.yml`:

```yaml
name: Validate

on:
  push:
  pull_request:
  schedule:
    - cron: "0 4 * * 1"

jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master
  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration
```

`tests.yml`:

```yaml
name: Tests

on:
  push:
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest
```

- [ ] **Step 4: Write `README.md`**

English. Sections: logo (`docs/logo.webp`), what it does (read-only, no booking), installation via HACS custom repository + manual copy, configuration (three-step flow with screenshot-free text), entities table (7 entities with purpose and example values), automation example using the timestamp sensor, notes on polling/caching (5 min, 6 h future cache, 14-day lookahead) and the `bookable` semantics, development section (`uv sync --group dev`, `uv run pytest`, F5 with Docker: port check, `.env` overrides, onboarding at http://localhost:8123, restart after code changes with `ha: restart`), disclaimer that the API is undocumented and may change, license.

- [ ] **Step 5: Update the design doc**

In `docs/stavsnas_battaxi_home_assistant_design.md`: change `**Status:** Förslag för MVP` to `**Status:** MVP implementerad (se §31 och README.md)` and add any deviations discovered during implementation to §31.2 as new table rows.

- [ ] **Step 6: Final verification**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && ./dev/ha.sh status`
Expected: all tests pass, ruff clean, status prints container/port state.
