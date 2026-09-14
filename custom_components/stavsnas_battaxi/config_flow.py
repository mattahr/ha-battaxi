"""Config flow for Stavsnäs Båttaxi: line → from pier → to pier."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util

from .api import BattaxiApi, BattaxiApiError
from .const import CONF_DESTINATION, CONF_LINE, CONF_ORIGIN, DOMAIN, TIMEZONE
from .models import BattaxiLine, BattaxiPier, BattaxiRoute
from .routes import build_route, destination_pier_ids, origin_pier_ids

_LOGGER = logging.getLogger(__name__)


def _select(field: str, options: list[SelectOptionDict]) -> vol.Schema:
    """Build a one-field form schema with a searchable dropdown."""
    return vol.Schema(
        {
            vol.Required(field): SelectSelector(
                SelectSelectorConfig(
                    options=options, mode=SelectSelectorMode.DROPDOWN, sort=False
                )
            )
        }
    )


class BattaxiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._api: BattaxiApi | None = None
        self._lines: dict[str, BattaxiLine] = {}
        self._piers: dict[str, BattaxiPier] = {}
        self._line: BattaxiLine | None = None
        self._origin_id: str | None = None

    async def _async_api(self) -> BattaxiApi:
        """Lazily create the API client."""
        if self._api is None:
            self._api = BattaxiApi(
                async_get_clientsession(self.hass),
                timezone=await dt_util.async_get_time_zone(TIMEZONE),
            )
        return self._api

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: pick a line."""
        return await self._async_step_line("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure: pick a (possibly different) line."""
        return await self._async_step_line("reconfigure", user_input)

    async def _async_step_line(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if not self._lines:
            api = await self._async_api()
            try:
                piers, lines = await asyncio.gather(
                    api.async_get_piers(), api.async_get_lines()
                )
            except BattaxiApiError as err:
                _LOGGER.warning("Could not fetch Båttaxi reference data: %s", err)
                return self.async_abort(reason="cannot_connect")
            self._piers = {pier.id: pier for pier in piers}
            self._lines = {line.id: line for line in lines if origin_pier_ids(line)}
            if not self._lines:
                return self.async_abort(reason="no_lines")

        if user_input is not None:
            self._line = self._lines[user_input[CONF_LINE]]
            return await self.async_step_origin()

        options = [
            SelectOptionDict(value=line.id, label=line.name)
            for line in self._lines.values()
        ]
        return self.async_show_form(
            step_id=step_id, data_schema=_select(CONF_LINE, options)
        )

    async def async_step_origin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step: pick the departure pier."""
        assert self._line is not None
        if user_input is not None:
            self._origin_id = user_input[CONF_ORIGIN]
            return await self.async_step_destination()

        return self.async_show_form(
            step_id="origin",
            data_schema=_select(
                CONF_ORIGIN, self._pier_options(origin_pier_ids(self._line))
            ),
            description_placeholders={"line": self._line.name},
        )

    async def async_step_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Third step: pick the arrival pier, verify the API and finish."""
        assert self._line is not None
        assert self._origin_id is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                route = build_route(
                    self._line,
                    self._piers,
                    self._origin_id,
                    user_input[CONF_DESTINATION],
                )
            except ValueError:
                errors["base"] = "invalid_route"
            else:
                api = await self._async_api()
                try:
                    # Zero departures is fine; we only verify the API accepts the ids.
                    await api.async_search(
                        route.origin_id,
                        route.destination_id,
                        dt_util.now(api.timezone).date(),
                    )
                except BattaxiApiError as err:
                    _LOGGER.warning("Could not verify route with Båttaxi API: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    return await self._async_finish(route)

        origin = self._piers.get(self._origin_id)
        return self.async_show_form(
            step_id="destination",
            data_schema=_select(
                CONF_DESTINATION,
                self._pier_options(destination_pier_ids(self._line, self._origin_id)),
            ),
            errors=errors,
            description_placeholders={
                "line": self._line.name,
                "origin": origin.name if origin else self._origin_id,
            },
        )

    async def _async_finish(self, route: BattaxiRoute) -> ConfigFlowResult:
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if route.unique_id != entry.unique_id:
                await self.async_set_unique_id(route.unique_id)
                self._abort_if_unique_id_configured()
            return self.async_update_reload_and_abort(
                entry,
                unique_id=route.unique_id,
                title=route.title,
                data=route.as_config(),
            )

        await self.async_set_unique_id(route.unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=route.title, data=route.as_config())

    def _pier_options(self, pier_ids: list[str]) -> list[SelectOptionDict]:
        return [
            SelectOptionDict(value=pier_id, label=self._piers[pier_id].name)
            for pier_id in pier_ids
            if pier_id in self._piers
        ]
