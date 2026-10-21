"""The data coordinator for the Felicity Solar integration.

The coordinator is the single source of truth for the entities. It is fed by
two transports:

* a **WebSocket** that pushes live snapshots (the preferred path, mirroring
  the FSolar web app);
* **REST polling**, used as a fallback when the socket cannot be established
  or when it drops.

Both paths publish into the same coordinator, so the entities never see two
different update mechanisms.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_SERIALS,
    CONF_ENABLE_ALERTS,
    CONF_ENABLE_PLANT_FLOW,
    CONF_PLANT_ID,
    CONF_POLL_INTERVAL,
    CONF_SCAN_DEVICES,
    CONF_SCAN_INTERVAL,
    CONF_USE_WEBSOCKET,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .counters import LifetimeCounters
from .vendor.felicity_client import (
    Alert,
    Device,
    EnergyFlow,
    FelicityAuthError,
    FelicityClient,
    FelicityError,
    FelicityTokenExpiredError,
    PlantDetails,
    ProductType,
    Snapshot,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class FelicityData:
    """Everything the coordinator knows about the configured plant."""

    devices: dict[str, Device] = field(default_factory=dict)
    snapshots: dict[str, Snapshot] = field(default_factory=dict)
    flows: dict[str, EnergyFlow] = field(default_factory=dict)
    plant_details: PlantDetails | None = None
    counters: LifetimeCounters | None = None
    alerts: list[Alert] = field(default_factory=list)
    source: str = "rest"
    last_update: Any = None

    def device_for(self, serial_number: str) -> Device | None:
        """Return the metadata of a device."""
        return self.devices.get(serial_number)


FelicityConfigEntry = ConfigEntry


class FelicityCoordinator(DataUpdateCoordinator[FelicityData]):
    """Fetch and keep the Felicity Solar data up to date."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FelicityConfigEntry,
        client: FelicityClient,
        store: Store[dict[str, Any]] | None = None,
    ) -> None:
        """Initialise the coordinator."""
        self.entry = entry
        self.client = client
        self._ws_tasks: dict[str, asyncio.Task[None]] = {}
        self._ws_connected = False
        self._store = store
        self._counters: LifetimeCounters | None = None
        self._counters_dirty = False

        interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=interval),
            always_update=False,
        )

    @property
    def plant_id(self) -> str:
        """The plant this coordinator is bound to."""
        return str(self.entry.data.get(CONF_PLANT_ID, ""))

    @property
    def use_websocket(self) -> bool:
        """Whether the WebSocket transport is enabled."""
        return bool(
            self.entry.options.get(
                CONF_USE_WEBSOCKET, self.entry.data.get(CONF_USE_WEBSOCKET, True)
            )
        )

    @property
    def poll_interval(self) -> int:
        """The polling interval used when the socket is unavailable."""
        return int(
            self.entry.options.get(
                CONF_POLL_INTERVAL, self.entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            )
        )

    @property
    def plant_flow_enabled(self) -> bool:
        """Whether the plant-level energy flow is fetched."""
        return bool(
            self.entry.options.get(
                CONF_ENABLE_PLANT_FLOW, self.entry.data.get(CONF_ENABLE_PLANT_FLOW, True)
            )
        )

    @property
    def alerts_enabled(self) -> bool:
        """Whether the alarms are fetched."""
        return bool(
            self.entry.options.get(
                CONF_ENABLE_ALERTS, self.entry.data.get(CONF_ENABLE_ALERTS, True)
            )
        )

    @property
    def selected_serials(self) -> list[str]:
        """The serial numbers the user chose to expose."""
        return list(self.entry.data.get(CONF_DEVICE_SERIALS, []) or [])

    @property
    def scan_devices(self) -> bool:
        """Whether every device of the plant is exposed."""
        return bool(self.entry.data.get(CONF_SCAN_DEVICES, True))

    async def _async_update_data(self) -> FelicityData:
        """Fetch a full round of data from the FSolar API."""
        try:
            devices = await self.client.list_devices(plant_id=self.plant_id or None)
        except FelicityTokenExpiredError:
            # The client refreshes the token on its own; a second failure is
            # a genuine authentication problem.
            raise ConfigEntryAuthFailed from None
        except FelicityAuthError:
            raise ConfigEntryAuthFailed from None
        except FelicityError as exc:
            raise UpdateFailed(f"could not list the devices: {exc}") from exc

        wanted = self._wanted_serials(devices)
        snapshots = await self.client.get_snapshots(wanted)

        flows: dict[str, EnergyFlow] = {}
        if self.plant_flow_enabled and self.plant_id:
            for serial_number in wanted:
                try:
                    flows[serial_number] = await self.client.get_energy_flow(
                        serial_number, self.plant_id
                    )
                except FelicityError as exc:
                    _LOGGER.debug("Could not read the energy flow of %s: %s", serial_number, exc)

        alerts: list[Alert] = []
        if self.alerts_enabled:
            try:
                alerts = await self.client.list_alerts()
            except FelicityError as exc:
                _LOGGER.debug("Could not read the alerts: %s", exc)

        plant_details: PlantDetails | None = None
        if self.plant_id:
            try:
                plant_details = await self.client.get_plant_details(self.plant_id)
            except FelicityError as exc:
                _LOGGER.debug("Could not read the plant details: %s", exc)

        counters = self._update_counters(plant_details)

        data = FelicityData(
            devices={device.serial_number: device for device in devices},
            snapshots=snapshots,
            flows=flows,
            plant_details=plant_details,
            counters=counters,
            alerts=alerts,
            source="websocket" if self._ws_connected else "rest",
            last_update=self.last_update_success,
        )
        await self.async_persist_counters()
        _LOGGER.debug(
            "Fetched %s device(s), %s snapshot(s), %s alert(s) via %s",
            len(data.devices),
            len(data.snapshots),
            len(data.alerts),
            data.source,
        )
        return data

    def restore_counters(self, counters: LifetimeCounters) -> None:
        """Adopt the counters that were persisted by a previous run."""
        self._counters = counters

    def _wanted_serials(self, devices: list[Device]) -> list[str]:
        """Return the serial numbers that should be polled."""
        if self.scan_devices:
            return [device.serial_number for device in devices]
        selected = set(self.selected_serials)
        return [device.serial_number for device in devices if device.serial_number in selected]

    @property
    def primary_flow(self) -> EnergyFlow | None:
        """The energy flow of the **inverter** of the plant.

        The plant reports a flow per device, and the order in which the
        devices are returned is not guaranteed: on one plant the inverter
        comes first, on another one the battery does. The plant level
        sensors describe the production and the consumption of the whole
        plant, so they have to read the inverter's flow, not the first one
        that happens to be in the list.
        """
        data = self.data
        if data is None:
            return None

        inverter: EnergyFlow | None = None
        fallback: EnergyFlow | None = None
        for serial_number, flow in data.flows.items():
            device = data.devices.get(serial_number)
            if device is not None and device.product_type is ProductType.INVERTER:
                inverter = flow
                break
            if fallback is None and flow.pv_power is not None:
                fallback = flow
        return inverter or fallback

    def _update_counters(self, details: PlantDetails | None) -> LifetimeCounters | None:
        """Accumulate the lifetime counters and persist them.

        The counters have to survive a restart, otherwise every restart
        would reset the Energy Dashboard totals.
        """
        if details is None:
            return self._counters
        if self._counters is None:
            self._counters = LifetimeCounters()
        self._counters.update(details)
        self._counters_dirty = True
        return self._counters

    async def async_persist_counters(self) -> None:
        """Write the accumulated counters to the store, if they changed."""
        if not self._counters_dirty or self._counters is None:
            return
        await self._store.async_save(self._counters.to_dict())
        self._counters_dirty = False

    async def async_start_websocket(self) -> None:
        """Start the WebSocket listener, if enabled."""
        if not self.use_websocket or self._ws_tasks:
            return

        devices = await self.client.list_devices(plant_id=self.plant_id or None)
        serial_numbers = self._wanted_serials(devices)
        if not serial_numbers:
            _LOGGER.info("No device to stream, the WebSocket stays off")
            return

        for serial_number in serial_numbers:
            self._ws_tasks[serial_number] = self.hass.async_create_background_task(
                self._async_websocket_loop(serial_number),
                name=f"{DOMAIN}_websocket_{self.entry.entry_id}_{serial_number}",
            )
        _LOGGER.info("Started %s WebSocket stream(s)", len(self._ws_tasks))

    async def async_stop_websocket(self) -> None:
        """Stop the WebSocket listener."""
        for task in self._ws_tasks.values():
            task.cancel()
        for task in self._ws_tasks.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._ws_tasks.clear()
        self._ws_connected = False

    async def _async_websocket_loop(self, serial_number: str) -> None:
        """Consume the live snapshots of one device and publish them."""
        device = (self.data.devices if self.data else {}).get(serial_number)
        collector_sn = (device.raw.get("collectorSn") if device else None) or ""

        try:
            async for snapshot in self.client.realtime.stream_device(
                serial_number, str(collector_sn)
            ):
                self._ws_connected = True
                self.async_set_updated_data(self._merge_snapshot(snapshot))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the fallback is the REST polling
            _LOGGER.warning(
                "The WebSocket stream for %s stopped (%s), the REST polling takes over",
                serial_number,
                exc,
            )

    def _merge_snapshot(self, snapshot: Snapshot) -> FelicityData:
        """Merge a pushed snapshot into the current data."""
        data = self.data or FelicityData()
        data.snapshots[snapshot.device_sn] = snapshot
        data.source = "websocket"
        data.last_update = self.hass.loop.time()
        return data
