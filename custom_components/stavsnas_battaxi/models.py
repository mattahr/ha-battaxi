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
