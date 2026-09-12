"""Tests for deriving directed routes from a line's ordered stops."""

import pytest

from custom_components.stavsnas_battaxi.api import parse_lines, parse_piers
from custom_components.stavsnas_battaxi.models import BattaxiLine, BattaxiPier
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
def piers_by_id() -> dict[str, BattaxiPier]:
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


def test_build_route(
    sandhamn_line: BattaxiLine, piers_by_id: dict[str, BattaxiPier]
) -> None:
    route = build_route(sandhamn_line, piers_by_id, STAVSNAS, TELEGRAFHOLMEN)
    assert route.line_name == "Sandhamnslinjen"
    assert route.origin_name == "Stavsnäs"
    assert route.destination_name == "Telegrafholmen"
    assert route.unique_id == f"{LINE_ID}:{STAVSNAS}:{TELEGRAFHOLMEN}"


def test_build_route_rejects_invalid_pair(
    sandhamn_line: BattaxiLine, piers_by_id: dict[str, BattaxiPier]
) -> None:
    with pytest.raises(ValueError):
        build_route(sandhamn_line, piers_by_id, STAVSNAS, STAVSNAS)
    with pytest.raises(ValueError):
        build_route(sandhamn_line, piers_by_id, STAVSNAS, "unknown-pier")
    with pytest.raises(ValueError):
        build_route(sandhamn_line, {}, STAVSNAS, TELEGRAFHOLMEN)
