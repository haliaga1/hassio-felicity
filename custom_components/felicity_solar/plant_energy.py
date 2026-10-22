"""Plant level energy sensors.

They read ``POST /plant/plantDetails``, the only endpoint that exposes the
**daily energy counters** of the plant: the grid import and export, the
battery charge and discharge, and the accumulated photovoltaic production.

The daily counters reset at the plant's local midnight, so they are
declared with ``state_class=TOTAL`` and a ``last_reset`` of midnight — the
way Home Assistant expects a periodic counter. The accumulated production
only grows and is declared ``TOTAL_INCREASING``, which is what the Energy
Dashboard needs.

The **lifetime** counters of the grid and the battery are accumulated from
the daily ones, because the API does not publish them; see
:mod:`custom_components.felicity_solar.counters`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FelicityCoordinator, FelicityData, select_primary_flow
from .counters import LifetimeCounters
from .entity import FelicityEntity
from .vendor.felicity_client.models.common import ProductType
from .vendor.felicity_client.models.plant_details import PlantDetails

_LOGGER = logging.getLogger(__name__)

DetailsFn = Callable[[PlantDetails], float | None]
CounterFn = Callable[[LifetimeCounters], float | None]
DataFn = Callable[["FelicityData"], float | None]


@dataclass(frozen=True, kw_only=True)
class FelicityPlantEnergyEntityDescription(SensorEntityDescription):
    """A plant energy sensor description."""

    details_fn: DetailsFn
    #: Set for the sensors that read the accumulated counters instead of the
    #: plant details.
    counter_fn: CounterFn | None = None
    #: Set for the sensors that read the data of the plant's inverter.
    data_fn: DataFn | None = None
    #: Whether the counter resets every day.
    resets_daily: bool = False


def _load_total(data: FelicityData) -> float | None:
    """The lifetime AC output of the plant's inverter.

    It is the energy the installation has served to the house, which is what
    the Home Assistant Energy Dashboard needs to break the consumption down
    by plant.
    """
    for serial_number, device in data.devices.items():
        if device.product_type is not ProductType.INVERTER:
            continue
        snapshot = data.snapshots.get(serial_number)
        if snapshot is not None:
            return snapshot.ac_in.energy_total_kwh
    return None


def _pv_total(details: PlantDetails) -> float | None:
    return details.accumulated_pv_kwh


def _pv_today(details: PlantDetails) -> float | None:
    return details.today_pv_kwh


def _pv_month(details: PlantDetails) -> float | None:
    return details.month_pv_kwh


def _load_today(details: PlantDetails) -> float | None:
    return details.today_load_kwh


def _grid_import_today(details: PlantDetails) -> float | None:
    return details.today_grid_input_kwh


def _grid_export_today(details: PlantDetails) -> float | None:
    return details.today_feed_output_kwh


def _self_consumption_today(details: PlantDetails) -> float | None:
    return details.today_self_consumption_kwh


def _rated_power(details: PlantDetails) -> float | None:
    return details.rated_power_kwp


def _flow_power(data: FelicityData, attribute: str, positive: bool) -> float | None:
    """One half of a signed power of the plant's inverter.

    The Home Assistant Energy Dashboard needs the charging and the
    discharging power of the battery, and the import and the export of the
    grid, as separate sensors to draw the real-time flow.
    """
    flow = select_primary_flow(data)
    if flow is None:
        return None
    value = getattr(flow, attribute, None)
    if value is None:
        return None
    return max(0.0, value) if positive else max(0.0, -value)


PLANT_ENERGY_DESCRIPTIONS: tuple[FelicityPlantEnergyEntityDescription, ...] = (
    FelicityPlantEnergyEntityDescription(
        key="plant_pv_energy_total",
        translation_key="plant_pv_energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=_pv_total,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_pv_energy_today",
        translation_key="plant_pv_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=_pv_today,
        resets_daily=True,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_load_energy_total",
        translation_key="plant_load_energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=lambda _details: None,
        data_fn=_load_total,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_pv_energy_month",
        translation_key="plant_pv_energy_month",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=_pv_month,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_load_energy_today",
        translation_key="plant_load_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=_load_today,
        resets_daily=True,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_grid_import_today",
        translation_key="plant_grid_import_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=_grid_import_today,
        resets_daily=True,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_grid_export_today",
        translation_key="plant_grid_export_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=_grid_export_today,
        resets_daily=True,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_battery_charging_today",
        translation_key="plant_battery_charging_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=lambda _details: None,
        counter_fn=lambda counters: counters.battery_charging_today_kwh,
        resets_daily=True,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_battery_discharge_today",
        translation_key="plant_battery_discharge_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=lambda _details: None,
        counter_fn=lambda counters: counters.battery_discharging_today_kwh,
        resets_daily=True,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_self_consumption_today",
        translation_key="plant_self_consumption_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=_self_consumption_today,
        resets_daily=True,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_rated_power",
        translation_key="plant_rated_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        details_fn=_rated_power,
    ),
    # Las potencias separadas que necesita el flujo en tiempo real del
    # panel de Energia de Home Assistant.
    FelicityPlantEnergyEntityDescription(
        key="plant_battery_charging_power",
        translation_key="plant_battery_charging_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        details_fn=lambda _details: None,
        data_fn=lambda data: _flow_power(data, "battery_power", True),
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_battery_discharging_power",
        translation_key="plant_battery_discharging_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        details_fn=lambda _details: None,
        data_fn=lambda data: _flow_power(data, "battery_power", False),
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_grid_import_power",
        translation_key="plant_grid_import_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        details_fn=lambda _details: None,
        data_fn=lambda data: _flow_power(data, "grid_ac_input_power", True),
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_grid_export_power",
        translation_key="plant_grid_export_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        details_fn=lambda _details: None,
        data_fn=lambda data: _flow_power(data, "grid_ac_input_power", False),
    ),
    # --- Lifetime counters, accumulated from the daily ones -------------
    FelicityPlantEnergyEntityDescription(
        key="plant_grid_import_total",
        translation_key="plant_grid_import_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=lambda _details: None,
        counter_fn=lambda counters: counters.grid_import_kwh,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_grid_export_total",
        translation_key="plant_grid_export_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=lambda _details: None,
        counter_fn=lambda counters: counters.grid_export_kwh,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_battery_charging_total",
        translation_key="plant_battery_charging_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=lambda _details: None,
        counter_fn=lambda counters: counters.battery_charging_kwh,
    ),
    FelicityPlantEnergyEntityDescription(
        key="plant_battery_discharging_total",
        translation_key="plant_battery_discharging_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        details_fn=lambda _details: None,
        counter_fn=lambda counters: counters.battery_discharging_kwh,
    ),
)


async def async_setup_entry(
    hass: Any,
    entry: Any,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the plant energy sensors."""
    coordinator: FelicityCoordinator = hass.data[DOMAIN][entry.entry_id]
    plant_name = str(entry.data.get("plant_name") or entry.title)
    entities: list[FelicityEntity] = [
        FelicityPlantEnergySensor(coordinator, plant_name, description)
        for description in PLANT_ENERGY_DESCRIPTIONS
    ]
    async_add_entities(entities)
    _LOGGER.info("Added %s plant energy sensor(s)", len(entities))


class FelicityPlantEnergySensor(FelicityEntity, SensorEntity):
    """A sensor backed by a plant energy counter."""

    entity_description: FelicityPlantEnergyEntityDescription

    def __init__(
        self,
        coordinator: FelicityCoordinator,
        plant_name: str,
        description: FelicityPlantEnergyEntityDescription,
    ) -> None:
        """Initialise the plant energy sensor."""
        from .vendor.felicity_client.models.common import Device, ProductType

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
    def last_reset(self) -> Any:
        """The start of the current day, for the counters that reset daily."""
        if not self.entity_description.resets_daily:
            return None
        return dt_util.start_of_local_day(dt_util.now())

    @property
    def native_value(self) -> Any:
        """The value of the sensor."""
        if self.entity_description.data_fn is not None:
            return self.entity_description.data_fn(self.data)
        if self.entity_description.counter_fn is not None:
            counters = self.data.counters
            if counters is None:
                return None
            return self.entity_description.counter_fn(counters)

        details = self.data.plant_details
        if details is None:
            return None
        return self.entity_description.details_fn(details)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the plant metadata."""
        details = self.data.plant_details
        attributes: dict[str, Any] = {
            "plant_id": self.coordinator.plant_id,
            "plant_name": self._device.plant_name,
            "source": self.data.source,
        }
        if details is not None:
            attributes["device_count"] = details.device_count
            attributes["online_device_count"] = details.online_device_count
            attributes["rated_power_kwp"] = details.rated_power_kwp
            attributes["business_time_zone"] = details.business_time_zone
        return attributes
