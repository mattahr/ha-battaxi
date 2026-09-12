"""Tests for the config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

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
def mock_setup_entry() -> Generator[AsyncMock]:
    with patch(
        "custom_components.stavsnas_battaxi.async_setup_entry", return_value=True
    ) as mock:
        yield mock


def option_values(result: dict, field: str) -> list[str]:
    """Return the option values of a SelectSelector field in a form result."""
    schema = result["data_schema"].schema
    selector = next(value for key, value in schema.items() if key == field)
    return [option["value"] for option in selector.config["options"]]


async def start_user_flow(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def configure(hass: HomeAssistant, result: dict, data: dict) -> dict:
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def test_full_user_flow(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, mock_setup_entry: AsyncMock
) -> None:
    result = await start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert LINE_ID in option_values(result, CONF_LINE)

    result = await configure(hass, result, {CONF_LINE: LINE_ID})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "origin"
    assert option_values(result, CONF_ORIGIN) == [
        STAVSNAS,
        SANDHAMN,
        TELEGRAFHOLMEN,
        TROUVILLE,
        LOKHOLMEN,
    ]

    result = await configure(hass, result, {CONF_ORIGIN: STAVSNAS})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "destination"
    assert result["description_placeholders"] == {
        "line": "Sandhamnslinjen",
        "origin": "Stavsnäs",
    }
    assert option_values(result, CONF_DESTINATION) == [
        SANDHAMN,
        TELEGRAFHOLMEN,
        TROUVILLE,
        LOKHOLMEN,
    ]

    result = await configure(hass, result, {CONF_DESTINATION: TELEGRAFHOLMEN})
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
    result = await start_user_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_no_lines_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(PIERS_URL, json=load_json("piers.json"))
    aioclient_mock.get(LINES_URL, json={"items": []})
    result = await start_user_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_lines"


async def test_duplicate_route_aborts(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    config_entry.add_to_hass(hass)
    result = await start_user_flow(hass)
    result = await configure(hass, result, {CONF_LINE: LINE_ID})
    result = await configure(hass, result, {CONF_ORIGIN: STAVSNAS})
    result = await configure(hass, result, {CONF_DESTINATION: TELEGRAFHOLMEN})
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

    result = await start_user_flow(hass)
    result = await configure(hass, result, {CONF_LINE: LINE_ID})
    result = await configure(hass, result, {CONF_ORIGIN: STAVSNAS})
    result = await configure(hass, result, {CONF_DESTINATION: TELEGRAFHOLMEN})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "destination"
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(SEARCH_URL, json=load_json("search_empty.json"))
    result = await configure(hass, result, {CONF_DESTINATION: TELEGRAFHOLMEN})
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

    result = await configure(hass, result, {CONF_LINE: LINE_ID})
    assert result["step_id"] == "origin"
    result = await configure(hass, result, {CONF_ORIGIN: STAVSNAS})
    assert result["step_id"] == "destination"
    result = await configure(hass, result, {CONF_DESTINATION: SANDHAMN})
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
        data={
            **ROUTE_DATA,
            "destination_id": SANDHAMN,
            "destination_name": "Sandhamn",
        },
    )
    other.add_to_hass(hass)
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, {CONF_LINE: LINE_ID})
    result = await configure(hass, result, {CONF_ORIGIN: STAVSNAS})
    result = await configure(hass, result, {CONF_DESTINATION: SANDHAMN})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
