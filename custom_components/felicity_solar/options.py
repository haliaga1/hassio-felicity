"""Options flow for the Felicity Solar integration.

Besides the tuning knobs, the options flow offers the action that cannot
be reached from the config flow once an entry exists: **add another account
or plant**. It starts a second config flow, so a second installation can be
added from the integration page instead of having to go through "Add
integration" again.

Moving an entry to another plant is done with the standard **Reconfigure**
button of the integration page, which calls ``async_step_reconfigure`` of
the config flow.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow

from .const import (
    CONF_ENABLE_ALERTS,
    CONF_ENABLE_PLANT_FLOW,
    CONF_POLL_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_USE_WEBSOCKET,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

MENU_ADD_ACCOUNT = "add_account"
MENU_TUNING = "tuning"


class FelicitySolarOptionsFlow(OptionsFlow):
    """Let the user tune the refresh behaviour and manage the installations."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise the options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the menu of the available actions."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[MENU_TUNING, MENU_ADD_ACCOUNT],
        )

    async def async_step_tuning(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and store the tuning options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        data = self._config_entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(
                        CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ),
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=options.get(
                        CONF_POLL_INTERVAL, data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
                    ),
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
                vol.Required(
                    CONF_USE_WEBSOCKET,
                    default=options.get(CONF_USE_WEBSOCKET, data.get(CONF_USE_WEBSOCKET, True)),
                ): bool,
                vol.Required(
                    CONF_ENABLE_PLANT_FLOW,
                    default=options.get(
                        CONF_ENABLE_PLANT_FLOW, data.get(CONF_ENABLE_PLANT_FLOW, True)
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_ALERTS,
                    default=options.get(CONF_ENABLE_ALERTS, data.get(CONF_ENABLE_ALERTS, True)),
                ): bool,
            }
        )
        return self.async_show_form(step_id="tuning", data_schema=schema)

    async def async_step_add_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start a second config flow to add another account or plant.

        The new flow is started in the background; Home Assistant shows it
        as a dialog the user completes.
        """
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"started_from": "options"},
        )
        return self.async_abort(reason="new_flow_started")
