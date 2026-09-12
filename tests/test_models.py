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
