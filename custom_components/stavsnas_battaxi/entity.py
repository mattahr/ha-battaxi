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
