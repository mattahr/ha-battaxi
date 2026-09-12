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
        """Return True when bookable, None when there is no next departure."""
        if self.data.next_departure is None:
            return None
        return self.data.next_departure.bookable
