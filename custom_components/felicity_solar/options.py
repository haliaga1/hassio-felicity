"""Options flow for the Felicity Solar integration."""

from __future__ import annotations

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
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _interval_schema(default: int) -> vol.Schema:
    """Build a numeric interval selector."""
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=default,
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
        }
    )


class FelicitySolarOptionsFlow(OptionsFlow):
    """Let the user tune the refresh behaviour."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise the options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and store the options."""
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
        return self.async_show_form(step_id="init", data_schema=schema)
