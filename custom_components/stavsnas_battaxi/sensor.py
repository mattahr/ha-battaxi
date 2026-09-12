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


def _next_departure(data: BattaxiData, _: BattaxiRoute) -> datetime | None:
    return data.next_departure.departure if data.next_departure else None


def _next_arrival(data: BattaxiData, _: BattaxiRoute) -> datetime | None:
    return data.next_departure.arrival if data.next_departure else None


def _available_seats(data: BattaxiData, _: BattaxiRoute) -> int | None:
    return data.next_departure.available_seats if data.next_departure else None


def _next_departure_text(data: BattaxiData, route: BattaxiRoute) -> str | None:
    return format_next_departure(data.next_departure, route, data.today)


def _departures_today(data: BattaxiData, _: BattaxiRoute) -> int:
    return len(data.departures_today)


def _departures_today_text(data: BattaxiData, _: BattaxiRoute) -> str:
    return format_departures_today(data.departures_today)


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


def _departures_today_attributes(data: BattaxiData, _: BattaxiRoute) -> dict[str, Any]:
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
        value_fn=_next_departure,
        attributes_fn=_next_departure_attributes,
    ),
    BattaxiSensorEntityDescription(
        key="next_departure_text",
        translation_key="next_departure_text",
        value_fn=_next_departure_text,
    ),
    BattaxiSensorEntityDescription(
        key="next_arrival",
        translation_key="next_arrival",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_arrival,
    ),
    BattaxiSensorEntityDescription(
        key="available_seats",
        translation_key="available_seats",
        value_fn=_available_seats,
    ),
    BattaxiSensorEntityDescription(
        key="departures_today",
        translation_key="departures_today",
        value_fn=_departures_today,
        attributes_fn=_departures_today_attributes,
    ),
    BattaxiSensorEntityDescription(
        key="departures_today_text",
        translation_key="departures_today_text",
        value_fn=_departures_today_text,
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
