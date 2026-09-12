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
    """Format '17:30 Stavsnäs → 18:05 Telegrafholmen · 42 lediga'.

    Departures on another day than today get a 'D/M ' prefix.
    """
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
    """Format '15:10 – 12 platser | 17:10 | 19:40 – 47 platser'."""
    if not departures:
        return NO_MORE_DEPARTURES_TODAY
    items = []
    for departure in departures:
        item = format_clock(departure.departure)
        if departure.available_seats is not None:
            item += f" – {departure.available_seats} platser"
        items.append(item)
    return _truncate(LIST_SEPARATOR.join(items))
