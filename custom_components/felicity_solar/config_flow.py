"""The Felicity Solar config flow."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    API_URLS,
    CONF_API_NODE,
    CONF_DEVICE_SERIALS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    CONF_SCAN_DEVICES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    WS_URLS,
)
from .vendor.felicity_client import FelicityAuthError, FelicityClient
from .vendor.felicity_client.exceptions import FelicityError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_API_NODE, default="INT"): vol.In(["INT", "EU"]),
    }
)


def _slug(value: str) -> str:
    """Turn a plant or device name into an entity-id friendly slug."""
    return "-".join(part for part in value.lower().split() if part) or "felicity"


def _build_client(email: str, password: str, node: str) -> FelicityClient:
    """Build a client for the given account.

    The client owns its own ``httpx`` session on purpose: Home Assistant's
    shared session is an ``aiohttp`` session, and the FSolar TLS policy
    (verification always on, never ``ssl=False``) has to stay under the
    control of the library.
    """
    return FelicityClient(
        email,
        password,
        base_url=API_URLS.get(node, API_URLS["INT"]),
        ws_url=WS_URLS.get(node, WS_URLS["INT"]),
    )


class FelicitySolarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the configuration of a Felicity Solar account."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._email: str = ""
        self._password: str = ""
        self._node: str = "INT"
        self._plants: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the credentials and validate them."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._node = user_input.get(CONF_API_NODE, "INT")

            client = _build_client(self._email, self._password, self._node)
            try:
                async with client:
                    plants = await client.list_plants()
            except FelicityAuthError:
                errors["base"] = "invalid_auth"
            except FelicityError as exc:
                _LOGGER.error("Could not reach the FSolar API: %s", exc)
                errors["base"] = "cannot_connect"
            except Exception as exc:
                _LOGGER.exception("Unexpected error while authenticating: %s", exc)
                errors["base"] = "unknown"
            else:
                if not plants:
                    errors["base"] = "no_plants"
                else:
                    self._plants = {plant.id: plant.name for plant in plants}
                    await self.async_set_unique_id(self._email.lower())
                    self._abort_if_unique_id_configured()
                    if len(self._plants) == 1:
                        # A single installation needs no extra step.
                        plant_id = next(iter(self._plants))
                        return self._async_create_entry(plant_id)
                    return await self.async_step_plant()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_plant(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Let the user pick the plant to expose."""
        errors: dict[str, str] = {}

        if user_input is not None:
            plant_id = user_input[CONF_PLANT_ID]
            return self._async_create_entry(plant_id)

        options = [{"value": plant_id, "label": name} for plant_id, name in self._plants.items()]
        schema = vol.Schema(
            {
                vol.Required(CONF_PLANT_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="plant",
            data_schema=schema,
            errors=errors,
            description_placeholders={"plants": ", ".join(self._plants.values())},
        )

    def _async_create_entry(self, plant_id: str) -> ConfigFlowResult:
        """Create the config entry for the selected plant."""
        plant_name = self._plants.get(plant_id, plant_id)
        return self.async_create_entry(
            title=plant_name or "Felicity Solar",
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_PLANT_ID: plant_id,
                CONF_PLANT_NAME: plant_name,
                CONF_API_NODE: self._node,
                CONF_DEVICE_SERIALS: [],
                CONF_SCAN_DEVICES: True,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> Any:
        """Return the options flow handler."""
        from .options import FelicitySolarOptionsFlow

        return FelicitySolarOptionsFlow(config_entry)
