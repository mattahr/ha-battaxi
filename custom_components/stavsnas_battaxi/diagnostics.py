"""Diagnostics support for Stavsnäs Båttaxi."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import BattaxiConfigEntry
from .models import BattaxiDeparture


def _departure_summary(departure: BattaxiDeparture | None) -> dict[str, Any] | None:
    if departure is None:
        return None
    return {
        "id": departure.id,
        "line_id": departure.line_id,
        "departure": departure.departure.isoformat(),
        "arrival": departure.arrival.isoformat(),
        "available_seats": departure.available_seats,
        "bookable": departure.bookable,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BattaxiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (no credentials exist to redact)."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "route": dict(entry.data),
        "last_update_success": coordinator.last_update_success,
        "last_update": data.now.isoformat() if data else None,
        "today": data.today.isoformat() if data else None,
        "departures_today": len(data.departures_today) if data else None,
        "next_departure": _departure_summary(data.next_departure) if data else None,
        "cached_dates": coordinator.cache_summary(),
    }
