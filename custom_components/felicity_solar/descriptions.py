"""Entity descriptions for the Felicity Solar integration.

Each description maps one FSolar field to one Home Assistant entity. The
mapping rules that matter:

* the **native unit** is used (W, not kW); the conversion belongs in the
  Lovelace card, not in the sensor;
* a **lifetime counter** (``ePvTotal``, ``eLoadTotal``, ``totalEnergy``) is
  ``TOTAL_INCREASING`` so the Energy Dashboard can consume it;
* a **daily counter** (``ePvToday``, ``eLoadToday``) is ``MEASUREMENT`` on
  purpose: it resets every day, and declaring it as increasing would corrupt
  the long-term statistics;
* a **missing measurement** is ``None`` and makes the entity ``unavailable``,
  never a fabricated zero.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

from .vendor.felicity_client.models.common import ProductType
from .vendor.felicity_client.models.snapshot import Snapshot

__all__ = [
    "SENSOR_DESCRIPTIONS",
    "FelicitySensorEntityDescription",
]

ValueFn = Callable[[Snapshot], Any]


@dataclass(frozen=True, kw_only=True)
class FelicitySensorEntityDescription(SensorEntityDescription):
    """A sensor description bound to a FSolar field."""

    value_fn: ValueFn
    product_types: frozenset[ProductType] = frozenset()
    #: Whether the counter resets every day. Those sensors are declared with
    #: ``state_class=TOTAL`` and a ``last_reset`` of midnight, which is how
    #: Home Assistant expects a periodic counter to be reported.
    resets_daily: bool = False


def _pv_power(snapshot: Snapshot) -> float | None:
    return snapshot.pv.power


def _pv_total_power(snapshot: Snapshot) -> float | None:
    return snapshot.pv.total_power


def _pv_voltage(snapshot: Snapshot) -> float | None:
    return snapshot.pv.voltage


def _pv_current(snapshot: Snapshot) -> float | None:
    return snapshot.pv.current


def _pv_energy_today(snapshot: Snapshot) -> float | None:
    return snapshot.pv.energy_today_kwh


def _pv_energy_total(snapshot: Snapshot) -> float | None:
    return snapshot.pv.energy_total_kwh


def _grid_voltage(snapshot: Snapshot) -> float | None:
    return snapshot.ac_in.voltage


def _grid_frequency(snapshot: Snapshot) -> float | None:
    return snapshot.ac_in.frequency


def _grid_power(snapshot: Snapshot) -> float | None:
    return snapshot.ac_in.power


def _ac_output_voltage(snapshot: Snapshot) -> float | None:
    return snapshot.ac_out.voltage


def _ac_output_current(snapshot: Snapshot) -> float | None:
    return snapshot.ac_out.current


def _ac_output_power(snapshot: Snapshot) -> float | None:
    return snapshot.ac_out.power


def _load_percent(snapshot: Snapshot) -> float | None:
    return snapshot.ac_out.load_percent


def _battery_soc(snapshot: Snapshot) -> float | None:
    return snapshot.battery.soc


def _battery_soh(snapshot: Snapshot) -> float | None:
    return snapshot.battery.soh


def _battery_voltage(snapshot: Snapshot) -> float | None:
    return snapshot.battery.voltage


def _battery_current(snapshot: Snapshot) -> float | None:
    return snapshot.battery.current


def _battery_power(snapshot: Snapshot) -> float | None:
    return snapshot.battery.power


def _battery_capacity(snapshot: Snapshot) -> float | None:
    return snapshot.battery.capacity_kwh


def _battery_remaining_energy(snapshot: Snapshot) -> float | None:
    return snapshot.battery.remaining_energy_kwh


def _battery_charging_state(snapshot: Snapshot) -> str | None:
    state = snapshot.battery.charging_state_name
    return None if state == "unknown" and snapshot.battery.charging_state is None else state


def _cell_voltage_max(snapshot: Snapshot) -> float | None:
    return snapshot.battery.cell_voltage_max


def _cell_voltage_min(snapshot: Snapshot) -> float | None:
    return snapshot.battery.cell_voltage_min


def _battery_temp_max(snapshot: Snapshot) -> float | None:
    return snapshot.thermal.battery_max_c


def _battery_temp_min(snapshot: Snapshot) -> float | None:
    return snapshot.thermal.battery_min_c


def _device_temp_max(snapshot: Snapshot) -> float | None:
    return snapshot.thermal.device_max_c


def _total_energy(snapshot: Snapshot) -> float | None:
    return snapshot.totals.total_kwh


def _load_energy_today(snapshot: Snapshot) -> float | None:
    return snapshot.ac_in.energy_today_kwh


def _load_energy_total(snapshot: Snapshot) -> float | None:
    return snapshot.ac_in.energy_total_kwh


def _wifi_signal(snapshot: Snapshot) -> int | None:
    return snapshot.wifi_signal


def _work_mode(snapshot: Snapshot) -> str | None:
    return snapshot.work_mode


_INVERTER = ProductType.INVERTER
_BATTERY = ProductType.BATTERY
_CONTROLLER = ProductType.CONTROLLER
_POWER_TYPES = frozenset({_INVERTER, _CONTROLLER})
_BATTERY_TYPES = frozenset({_BATTERY, _INVERTER, _CONTROLLER})
_ALL_TYPES = frozenset({_INVERTER, _BATTERY, _CONTROLLER})


SENSOR_DESCRIPTIONS: tuple[FelicitySensorEntityDescription, ...] = (
    # --- Photovoltaic -------------------------------------------------
    FelicitySensorEntityDescription(
        key="pv_power",
        translation_key="pv_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_pv_power,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="pv_total_power",
        translation_key="pv_total_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_pv_total_power,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="pv_voltage",
        translation_key="pv_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=_pv_voltage,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="pv_current",
        translation_key="pv_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=_pv_current,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="pv_energy_today",
        translation_key="pv_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        # A counter that resets every day is reported as TOTAL with a
        # last_reset, never as TOTAL_INCREASING.
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_pv_energy_today,
        product_types=_POWER_TYPES,
        resets_daily=True,
    ),
    FelicitySensorEntityDescription(
        key="pv_energy_total",
        translation_key="pv_energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_pv_energy_total,
        product_types=_POWER_TYPES,
    ),
    # --- AC side ------------------------------------------------------
    FelicitySensorEntityDescription(
        key="grid_voltage",
        translation_key="grid_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=_grid_voltage,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="grid_frequency",
        translation_key="grid_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=2,
        value_fn=_grid_frequency,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_grid_power,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="ac_output_voltage",
        translation_key="ac_output_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=_ac_output_voltage,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="ac_output_current",
        translation_key="ac_output_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=_ac_output_current,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="ac_output_power",
        translation_key="ac_output_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_ac_output_power,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="load_percentage",
        translation_key="load_percentage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=_load_percent,
        product_types=_POWER_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="load_energy_today",
        translation_key="load_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_load_energy_today,
        product_types=_POWER_TYPES,
        resets_daily=True,
    ),
    FelicitySensorEntityDescription(
        key="load_energy_total",
        translation_key="load_energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_load_energy_total,
        product_types=_POWER_TYPES,
    ),
    # --- Battery ------------------------------------------------------
    FelicitySensorEntityDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=_battery_soc,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_soh",
        translation_key="battery_soh",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=_battery_soh,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value_fn=_battery_voltage,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_current",
        translation_key="battery_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=_battery_current,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_battery_power,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_capacity",
        translation_key="battery_capacity",
        device_class=SensorDeviceClass.ENERGY,
        # A quantity, not a flow: it has no statistics state class.
        state_class=None,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_battery_capacity,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_remaining_energy",
        translation_key="battery_remaining_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_battery_remaining_energy,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_charging_state",
        translation_key="battery_charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "charging", "discharging", "unknown"],
        value_fn=_battery_charging_state,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="cell_voltage_max",
        translation_key="cell_voltage_max",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        value_fn=_cell_voltage_max,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="cell_voltage_min",
        translation_key="cell_voltage_min",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        value_fn=_cell_voltage_min,
        product_types=_BATTERY_TYPES,
    ),
    # --- Thermal ------------------------------------------------------
    FelicitySensorEntityDescription(
        key="battery_temperature_max",
        translation_key="battery_temperature_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=_battery_temp_max,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="battery_temperature_min",
        translation_key="battery_temperature_min",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=_battery_temp_min,
        product_types=_BATTERY_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="device_temperature_max",
        translation_key="device_temperature_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=_device_temp_max,
        product_types=_BATTERY_TYPES,
    ),
    # --- Totals and misc ---------------------------------------------
    FelicitySensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_total_energy,
        product_types=_ALL_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value_fn=_wifi_signal,
        product_types=_ALL_TYPES,
    ),
    FelicitySensorEntityDescription(
        key="work_mode",
        translation_key="work_mode",
        value_fn=_work_mode,
        product_types=_ALL_TYPES,
    ),
)
