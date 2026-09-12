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
