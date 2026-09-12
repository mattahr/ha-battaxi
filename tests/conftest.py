"""Shared fixtures for the Stavsnäs Båttaxi tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

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
