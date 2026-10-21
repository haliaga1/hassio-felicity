"""Sensor platform for the Felicity Solar integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FelicityCoordinator, FelicityData
from .descriptions import SENSOR_DESCRIPTIONS, FelicitySensorEntityDescription
from .entity import FelicityEntity, slugify
from .plant_energy import (
    PLANT_ENERGY_DESCRIPTIONS,
    FelicityPlantEnergySensor,
)
from .vendor.felicity_client.models.common import Device, ProductType
from .vendor.felicity_client.models.energy import EnergyFlow
from .vendor.felicity_client.models.snapshot import Snapshot

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Felicity Solar sensors."""
    coordinator: FelicityCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[FelicityEntity] = []

    for device in _devices_to_expose(coordinator):
        for description in SENSOR_DESCRIPTIONS:
            if description.product_types and device.product_type not in description.product_types:
                continue
            entities.append(FelicitySolarSensor(coordinator, device, description))

    plant_name = str(entry.data.get("plant_name") or entry.title)
    if coordinator.plant_flow_enabled:
        entities.extend(
            FelicityPlantSensor(coordinator, plant_name, description)
            for description in PLANT_SENSOR_DESCRIPTIONS
        )
    entities.extend(
        FelicityPlantEnergySensor(coordinator, plant_name, description)
        for description in PLANT_ENERGY_DESCRIPTIONS
    )

    # Los sensores agregados se crean una sola vez para toda la instancia:
    # el Energy Dashboard de Home Assistant es uno solo, asi que las plantas
    # deben sumarse en una sola entidad. El flag en ``hass.data`` lo
    # garantiza, sea cual sea el orden en que se configuren las entradas.
    if not hass.data.get(_AGGREGATE_FLAG):
        hass.data[_AGGREGATE_FLAG] = True
        entities.extend(
            FelicityTotalSensor(hass, description) for description in TOTAL_DESCRIPTIONS
        )

    async_add_entities(entities)
    _LOGGER.info("Added %s Felicity Solar sensor(s)", len(entities))


def _devices_to_expose(coordinator: FelicityCoordinator) -> list[Device]:
    """Return the devices the user asked to expose."""
    devices = list((coordinator.data.devices if coordinator.data else {}).values())
    if coordinator.scan_devices:
        return devices
    selected = set(coordinator.selected_serials)
    return [device for device in devices if device.serial_number in selected]


class FelicitySolarSensor(FelicityEntity, SensorEntity):
    """A sensor backed by a field of the FSolar device snapshot."""

    entity_description: FelicitySensorEntityDescription

    def __init__(
        self,
        coordinator: FelicityCoordinator,
        device: Device,
        description: FelicitySensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, device, description)

    @property
    def _snapshot(self) -> Snapshot | None:
        """The latest snapshot of this device."""
        return self.data.snapshots.get(self._device.serial_number)

    @property
    def last_reset(self) -> datetime | None:
        """The start of the current day, for the counters that reset daily.

        Home Assistant requires a ``last_reset`` on every ``TOTAL`` sensor.
        The FSolar counters reset at the *device's* local midnight, which can
        differ from the Home Assistant timezone; the offset is at most a few
        hours and only shifts the daily statistics bucket.
        """
        if not self.entity_description.resets_daily:
            return None
        return dt_util.start_of_local_day(dt_util.now())

    @property
    def native_value(self) -> Any:
        """The value of the sensor."""
        snapshot = self._snapshot
        if snapshot is None:
            return None
        try:
            return self.entity_description.value_fn(snapshot)
        except (KeyError, TypeError, ValueError) as exc:
            _LOGGER.debug(
                "Could not read %s from %s: %s",
                self.entity_description.key,
                self._device.serial_number,
                exc,
            )
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Add the product type to the shared attributes."""
        attributes = super().extra_state_attributes
        attributes["product_type"] = self._device.product_type
        return attributes


FlowFn = Callable[[EnergyFlow], float | None]


@dataclass(frozen=True, kw_only=True)
class FelicityPlantSensorEntityDescription(SensorEntityDescription):
    """A plant sensor description bound to an energy flow field."""

    flow_fn: FlowFn
    #: Whether the sign of this flow has been confirmed against a live
    #: installation. Until then the attribute stays ``False``.
    sign_verified: bool = False


def _pv(flow: EnergyFlow) -> float | None:
    return flow.pv_power


def _load(flow: EnergyFlow) -> float | None:
    return flow.load_power


def _battery(flow: EnergyFlow) -> float | None:
    return flow.battery_power


def _grid(flow: EnergyFlow) -> float | None:
    return flow.grid_power


PLANT_SENSOR_DESCRIPTIONS: tuple[FelicityPlantSensorEntityDescription, ...] = (
    FelicityPlantSensorEntityDescription(
        key="plant_pv_power",
        translation_key="plant_pv_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        flow_fn=_pv,
    ),
    FelicityPlantSensorEntityDescription(
        key="plant_load_power",
        translation_key="plant_load_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        flow_fn=_load,
    ),
    FelicityPlantSensorEntityDescription(
        key="plant_battery_power",
        translation_key="plant_battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        flow_fn=_battery,
    ),
    FelicityPlantSensorEntityDescription(
        key="plant_grid_power",
        translation_key="plant_grid_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        flow_fn=_grid,
    ),
)


class FelicityPlantSensor(FelicityEntity, SensorEntity):
    """A sensor backed by the plant energy flow.

    The plant sensors describe the installation as a whole (production,
    consumption, battery and grid at the same time) rather than a single
    device.
    """

    entity_description: FelicityPlantSensorEntityDescription

    def __init__(
        self,
        coordinator: FelicityCoordinator,
        plant_name: str,
        description: FelicityPlantSensorEntityDescription,
    ) -> None:
        """Initialise the plant sensor."""
        device = Device(
            serial_number=f"plant-{coordinator.plant_id}",
            product_type=ProductType.UNKNOWN,
            plant_name=plant_name,
        )
        super().__init__(coordinator, device, description)
        self._attr_unique_id = f"{coordinator.plant_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """The virtual device that groups the plant level sensors."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"plant-{self.coordinator.plant_id}")},
            manufacturer="Felicity Solar",
            model="FSolar plant",
            name=self._device.plant_name or "Felicity Solar",
        )

    @property
    def available(self) -> bool:
        """A plant sensor is available as soon as the coordinator is."""
        return self.coordinator.last_update_success

    @property
    def _flow(self) -> EnergyFlow | None:
        """The energy flow of the first device that reported one."""
        for flow in self.data.flows.values():
            return flow
        return None

    @property
    def native_value(self) -> Any:
        """The value of the sensor."""
        flow = self._flow
        if flow is None:
            return None
        return self.entity_description.flow_fn(flow)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the sign caveat and the raw flow."""
        attributes: dict[str, Any] = {
            "plant_id": self.coordinator.plant_id,
            "plant_name": self._device.plant_name,
            "source": self.data.source,
            "sign_verified": self.entity_description.sign_verified,
        }
        flow = self._flow
        if flow is not None:
            attributes["flow"] = dict(flow.values)
        return attributes


def plant_entity_id(plant_name: str, key: str) -> str:
    """Build the expected entity id of a plant sensor."""
    return f"sensor.felicity_{slugify(plant_name)}_{key}"


@dataclass(frozen=True, kw_only=True)
class FelicityTotalEntityDescription(SensorEntityDescription):
    """A description of an aggregated sensor."""

    #: The attribute of the plant data to add up.
    attribute: str


#: The device the aggregate belongs to.
AGGREGATE_DEVICE = ("felicity_solar", "felicity_solar_aggregate")

#: Marks that the aggregate sensors have already been created.
_AGGREGATE_FLAG = f"{DOMAIN}_aggregate_created"

TOTAL_DESCRIPTIONS: tuple[FelicityTotalEntityDescription, ...] = (
    FelicityTotalEntityDescription(
        key="total_pv_energy",
        translation_key="total_pv_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        attribute="pv_energy_total",
    ),
    FelicityTotalEntityDescription(
        key="total_pv_power",
        translation_key="total_pv_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        attribute="pv_power",
    ),
    FelicityTotalEntityDescription(
        key="total_grid_import_energy",
        translation_key="total_grid_import_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        attribute="grid_import_total",
    ),
    FelicityTotalEntityDescription(
        key="total_grid_export_energy",
        translation_key="total_grid_export_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        attribute="grid_export_total",
    ),
    FelicityTotalEntityDescription(
        key="total_battery_charging_energy",
        translation_key="total_battery_charging_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        attribute="battery_charging_total",
    ),
    FelicityTotalEntityDescription(
        key="total_battery_discharging_energy",
        translation_key="total_battery_discharging_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        attribute="battery_discharging_total",
    ),
)


def _plant_value(data: FelicityData, attribute: str) -> float | None:
    """Read one aggregated attribute of a plant."""
    details = data.plant_details
    if details is None:
        return None
    if attribute == "pv_energy_total":
        return details.accumulated_pv_kwh
    if attribute == "pv_power":
        for flow in data.flows.values():
            return flow.pv_power
        return None
    counters = data.counters
    if counters is None:
        return None
    return {
        "grid_import_total": counters.grid_import_kwh,
        "grid_export_total": counters.grid_export_kwh,
        "battery_charging_total": counters.battery_charging_kwh,
        "battery_discharging_total": counters.battery_discharging_kwh,
    }.get(attribute)


class FelicityTotalSensor(CoordinatorEntity[FelicityCoordinator], SensorEntity):
    """A sensor that sums the same value over every configured plant."""

    _attr_has_entity_name = True
    entity_description: FelicityTotalEntityDescription

    def __init__(self, hass: HomeAssistant, description: FelicityTotalEntityDescription) -> None:
        """Initialise the aggregated sensor."""
        # The coordinator is only used to be notified of the updates; the
        # value is read from every coordinator of the domain.
        first = next(iter(hass.data.get(DOMAIN, {}).values()), None)
        if first is None:
            raise ValueError("no Felicity Solar coordinator is available")
        super().__init__(first)
        self.hass = hass
        self.entity_description = description
        self._attr_unique_id = f"felicity_solar_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={AGGREGATE_DEVICE},
            manufacturer="Felicity Solar",
            model="FSolar aggregate",
            name="Felicity Solar",
        )

    @property
    def _coordinators(self) -> list[FelicityCoordinator]:
        """Every coordinator of the integration."""
        return list(self.hass.data.get(DOMAIN, {}).values())

    @property
    def native_value(self) -> Any:
        """The sum of the value over every plant."""
        total = 0.0
        found = False
        for coordinator in self._coordinators:
            data = coordinator.data
            if data is None:
                continue
            value = _plant_value(data, self.entity_description.attribute)
            if value is None:
                continue
            total += value
            found = True
        return total if found else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the contribution of each plant."""
        attributes: dict[str, Any] = {"plant_count": len(self._coordinators)}
        for coordinator in self._coordinators:
            data = coordinator.data
            if data is None:
                continue
            name = data.plant_details.name if data.plant_details else coordinator.plant_id
            value = _plant_value(data, self.entity_description.attribute)
            attributes[str(name)] = value
        return attributes
