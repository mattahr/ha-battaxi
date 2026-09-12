"""DataUpdateCoordinator for one configured Båttaxi route."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import BattaxiApi, BattaxiApiError, BattaxiRateLimitError
from .const import DOMAIN, FUTURE_CACHE_TTL, MAX_LOOKAHEAD_DAYS, UPDATE_INTERVAL
from .models import BattaxiDeparture, BattaxiRoute

_LOGGER = logging.getLogger(__name__)

type BattaxiConfigEntry = ConfigEntry[BattaxiCoordinator]


@dataclass(slots=True)
class BattaxiData:
    """Coordinator data for one route."""

    today: date
    now: datetime
    departures_today: list[BattaxiDeparture]
    next_departure: BattaxiDeparture | None


@dataclass(slots=True)
class _CachedDay:
    fetched_at: datetime
    departures: list[BattaxiDeparture] = field(default_factory=list)


class BattaxiCoordinator(DataUpdateCoordinator[BattaxiData]):
    """Fetch departures for a route, caching future dates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BattaxiConfigEntry,
        api: BattaxiApi,
        route: BattaxiRoute,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {route.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self.api = api
        self.route = route
        self._cache: dict[date, _CachedDay] = {}

    def cache_summary(self) -> list[dict[str, Any]]:
        """Describe cached future dates (used by diagnostics)."""
        return [
            {
                "date": day.isoformat(),
                "fetched_at": cached.fetched_at.isoformat(),
                "departures": len(cached.departures),
            }
            for day, cached in sorted(self._cache.items())
        ]

    async def _async_update_data(self) -> BattaxiData:
        now = dt_util.now(self.api.timezone)
        today = now.date()
        self._purge_cache(today)

        try:
            departures_today = [
                departure
                for departure in await self._async_fetch_day(today)
                if departure.departure >= now
            ]
            next_departure = departures_today[0] if departures_today else None
            if next_departure is None:
                next_departure = await self._async_find_next_departure(today, now)
        except BattaxiRateLimitError as err:
            raise UpdateFailed("Båttaxi API rate limit hit, will retry later") from err
        except BattaxiApiError as err:
            raise UpdateFailed(f"Error fetching departures: {err}") from err

        if next_departure is not None:
            _LOGGER.debug(
                "Selected next departure at %s", next_departure.departure.isoformat()
            )
        return BattaxiData(
            today=today,
            now=now,
            departures_today=departures_today,
            next_departure=next_departure,
        )

    async def _async_find_next_departure(
        self, today: date, now: datetime
    ) -> BattaxiDeparture | None:
        """Look ahead day by day (cached) until a day with traffic is found."""
        for offset in range(1, MAX_LOOKAHEAD_DAYS + 1):
            day = today + timedelta(days=offset)
            departures = await self._async_cached_day(day, now)
            if departures:
                return departures[0]
        _LOGGER.debug("No departures within %d days", MAX_LOOKAHEAD_DAYS)
        return None

    async def _async_cached_day(
        self, day: date, now: datetime
    ) -> list[BattaxiDeparture]:
        cached = self._cache.get(day)
        if cached is not None and now - cached.fetched_at < FUTURE_CACHE_TTL:
            _LOGGER.debug("Using cached result for %s", day)
            return cached.departures
        departures = await self._async_fetch_day(day)
        self._cache[day] = _CachedDay(fetched_at=now, departures=departures)
        return departures

    async def _async_fetch_day(self, day: date) -> list[BattaxiDeparture]:
        """Fetch one day, keep only the configured line, sorted by departure."""
        departures = await self.api.async_search(
            self.route.origin_id, self.route.destination_id, day
        )
        selected = sorted(
            (d for d in departures if d.line_id == self.route.line_id),
            key=lambda d: d.departure,
        )
        _LOGGER.debug("Fetched %d departures for %s", len(selected), day)
        return selected

    def _purge_cache(self, today: date) -> None:
        for day in [day for day in self._cache if day <= today]:
            del self._cache[day]
