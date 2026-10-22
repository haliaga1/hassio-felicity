"""The Felicity Solar integration.

Reads the metrics of a Felicity Solar installation through the official
FSolar cloud (the same API the web app uses) and exposes them as Home
Assistant entities.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    API_URLS,
    CONF_API_NODE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    DOMAIN,
    WS_URLS,
)
from .coordinator import FelicityCoordinator
from .counters import LifetimeCounters
from .vendor.felicity_client import FelicityClient, StoredToken

_LOGGER = logging.getLogger(__name__)

#: Where the bearer token is cached, encrypted by Home Assistant.
TOKEN_STORAGE_KEY = f"{DOMAIN}.token"
TOKEN_STORAGE_VERSION = 1

#: Where the accumulated energy counters are cached.
COUNTERS_STORAGE_KEY = f"{DOMAIN}.counters"
COUNTERS_STORAGE_VERSION = 2


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Felicity Solar account from a config entry."""
    node = str(entry.data.get(CONF_API_NODE, "INT"))
    client = FelicityClient(
        str(entry.data[CONF_EMAIL]),
        str(entry.data[CONF_PASSWORD]),
        base_url=API_URLS.get(node, API_URLS["INT"]),
        ws_url=WS_URLS.get(node, WS_URLS["INT"]),
    )

    store: Store[dict[str, Any]] = Store(hass, TOKEN_STORAGE_VERSION, TOKEN_STORAGE_KEY)
    stored = await store.async_load()
    if stored:
        token = StoredToken.from_dict(stored)
        if token is not None and not token.is_expired:
            client.auth.restore(token)
            _LOGGER.debug("Restored a cached FSolar token for %s", entry.data[CONF_EMAIL])

    # Cada planta tiene sus propios contadores: la clave del store lleva el
    # identificador de la planta, o el de la entrada si no hay.
    counters_key = COUNTERS_STORAGE_KEY
    plant_id = entry.data.get(CONF_PLANT_ID)
    if plant_id:
        counters_key = f"{counters_key}.{plant_id}"
    else:
        counters_key = f"{counters_key}.{entry.entry_id}"
    counters_store: Store[dict[str, Any]] = Store(hass, COUNTERS_STORAGE_VERSION, counters_key)
    counters = LifetimeCounters()
    stored_counters = await counters_store.async_load()
    if stored_counters:
        counters = LifetimeCounters.from_dict(stored_counters)

    coordinator = FelicityCoordinator(hass, entry, client, store=counters_store)
    coordinator.restore_counters(counters)
    await coordinator.async_config_entry_first_refresh()
    await _async_cache_token(hass, store, entry, client)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.runtime_data = coordinator

    await coordinator.async_start_websocket()

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def _async_cache_token(
    hass: HomeAssistant,
    store: Store[dict[str, Any]],
    entry: ConfigEntry,
    client: FelicityClient,
) -> None:
    """Persist the bearer token so a restart does not force a new login."""
    token = client.auth.current_token
    if token is None:
        return
    payload = await store.async_load() or {}
    payload[str(entry.data[CONF_EMAIL])] = token.to_dict()
    await store.async_save(payload)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"])
    coordinator: FelicityCoordinator | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if coordinator is not None:
        await coordinator.async_stop_websocket()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up the cached token when the entry is removed."""
    store: Store[dict[str, Any]] = Store(hass, TOKEN_STORAGE_VERSION, TOKEN_STORAGE_KEY)
    stored = await store.async_load()
    if stored:
        stored.pop(str(entry.data.get(CONF_EMAIL, "")), None)
        await store.async_save(stored)
