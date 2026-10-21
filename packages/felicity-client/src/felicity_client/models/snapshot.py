"""Typed representation of a device snapshot.

A snapshot is the "live telemetry" payload of a single device. The FSolar
backend is inconsistent about which fields it populates depending on the
product type, so every field is optional: a missing measurement is ``None``,
never a fabricated zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .._coerce import to_float, to_int, to_str
from .common import ProductType

__all__ = [
    "ACReadings",
    "BatteryReadings",
    "EnergyTotals",
    "PVReadings",
    "Snapshot",
    "ThermalReadings",
]


@dataclass(frozen=True, slots=True)
class PVReadings:
    """Photovoltaic input measurements.

    A device can have several PV strings. ``pvPower`` is then only the
    *first* string, so the total (``pvTotalPower``) is preferred: on a live
    two-string installation, ``pvPower`` reported 1938 W while
    ``pvTotalPower`` reported 3990 W.
    """

    power: float | None = None
    total_power: float | None = None
    voltage: float | None = None
    current: float | None = None
    string_count: int | None = None
    energy_today_kwh: float | None = None
    energy_total_kwh: float | None = None
    energy_month_kwh: float | None = None


@dataclass(frozen=True, slots=True)
class ACReadings:
    """AC measurements for one side of the inverter (grid in or load out)."""

    voltage: float | None = None
    current: float | None = None
    frequency: float | None = None
    power: float | None = None
    load_percent: float | None = None
    energy_today_kwh: float | None = None
    energy_total_kwh: float | None = None


@dataclass(frozen=True, slots=True)
class BatteryReadings:
    """Battery / EMS measurements.

    The sign convention, confirmed on a live installation: a **positive**
    power and current mean the battery is **charging**.
    """

    soc: float | None = None
    soh: float | None = None
    voltage: float | None = None
    current: float | None = None
    power: float | None = None
    #: Nominal capacity, in the unit the vendor reports (Ah on the FLA
    #: family). It is **not** kWh, so it is not exposed as an energy sensor.
    capacity_raw: float | None = None
    capacity_unit: str | None = None
    remaining_energy_kwh: float | None = None
    total_ems_capacity_kwh: float | None = None
    charging_state: int | None = None
    bms_state: str | None = None
    cell_voltage_max: float | None = None
    cell_voltage_min: float | None = None
    cell_voltages: tuple[float, ...] = ()

    @property
    def charging_state_name(self) -> str:
        """Human readable charging state.

        Confirmed on a live FLA48100-EU: ``bmsChargingState == 1`` while the
        battery was charging (``bmsPower`` positive). ``0`` is idle. Any
        other value is reported as ``unknown`` rather than guessed.
        """
        if self.charging_state is None:
            return "unknown"
        return {0: "idle", 1: "charging"}.get(self.charging_state, "unknown")


@dataclass(frozen=True, slots=True)
class ThermalReadings:
    """Temperature sensors."""

    battery_max_c: float | None = None
    battery_min_c: float | None = None
    device_max_c: float | None = None
    device_min_c: float | None = None
    cell_temperatures: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class EnergyTotals:
    """Lifetime and period energy counters."""

    total_kwh: float | None = None
    total_unit: str | None = None
    energy_today_kwh: float | None = None
    energy_total_kwh: float | None = None


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A point-in-time view of one device."""

    device_sn: str
    product_type: ProductType
    timestamp: datetime | None = None
    model: str | None = None
    plant_name: str | None = None
    status: str | None = None
    work_mode: str | None = None
    firmware_version: str | None = None
    collector_sn: str | None = None
    rated_power: float | None = None
    rated_energy: float | None = None
    wifi_signal: int | None = None
    warning_count: int | None = None
    time_zone: str | None = None
    pv: PVReadings = field(default_factory=PVReadings)
    ac_in: ACReadings = field(default_factory=ACReadings)
    ac_out: ACReadings = field(default_factory=ACReadings)
    battery: BatteryReadings = field(default_factory=BatteryReadings)
    thermal: ThermalReadings = field(default_factory=ThermalReadings)
    totals: EnergyTotals = field(default_factory=EnergyTotals)
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Snapshot:
        """Build a snapshot from a ``/device/get_device_snapshot`` payload."""
        cell_voltages = _float_tuple(payload.get("bmsVoltageList"))
        cell_temps = _float_tuple(payload.get("cellTempList"))

        return cls(
            device_sn=to_str(payload.get("deviceSn")) or "",
            product_type=ProductType.parse(payload.get("productTypeEnum")),
            timestamp=_parse_timestamp(payload.get("dataTime"), payload.get("dataTimeStr")),
            model=to_str(payload.get("deviceModel")),
            plant_name=to_str(payload.get("plantName")),
            status=to_str(payload.get("status")),
            work_mode=to_str(payload.get("workModeStr")),
            firmware_version=to_str(payload.get("firmwareVersion")),
            collector_sn=to_str(payload.get("collectorSn")) or to_str(payload.get("collectorSn2")),
            rated_power=to_float(payload.get("ratedPower")),
            rated_energy=to_float(payload.get("ratedEnergy")),
            wifi_signal=to_int(payload.get("wifiSignal")),
            warning_count=to_int(payload.get("warningCount")),
            time_zone=to_str(payload.get("timeZone")),
            pv=PVReadings(
                # The total covers every PV string; pvPower is only the first.
                power=to_float(payload.get("pvTotalPower"), to_float(payload.get("pvPower"))),
                total_power=to_float(payload.get("pvTotalPower")),
                voltage=to_float(payload.get("pvVolt")),
                current=to_float(payload.get("pvInCurr")),
                string_count=to_int(payload.get("pvChannelNum")),
                energy_today_kwh=to_float(payload.get("ePvToday")),
                energy_total_kwh=to_float(
                    payload.get("ePvTotal"),
                    to_float(payload.get("ePvYear"), to_float(payload.get("totalEnergy"))),
                ),
                energy_month_kwh=to_float(payload.get("ePvMonth")),
            ),
            ac_in=ACReadings(
                voltage=to_float(payload.get("acRInVolt")),
                current=to_float(payload.get("acRInCurr")),
                frequency=to_float(payload.get("acRInFreq")),
                power=to_float(payload.get("acRInPower")),
                load_percent=to_float(payload.get("loadPercent")),
                energy_today_kwh=to_float(payload.get("eLoadToday")),
                energy_total_kwh=to_float(
                    payload.get("eLoadTotal"),
                    to_float(payload.get("eLoadYear"), to_float(payload.get("tLoadYear"))),
                ),
            ),
            ac_out=ACReadings(
                voltage=to_float(payload.get("acROutVolt")),
                current=to_float(payload.get("acROutCurr")),
                frequency=to_float(payload.get("acROutFreq")),
                power=to_float(payload.get("acTotalOutActPower")),
                load_percent=to_float(payload.get("loadPercent")),
            ),
            battery=BatteryReadings(
                # A battery reports its own ``battSoc``; the ``emsSoc`` of
                # the same payload is the aggregate of the whole installation
                # and can differ by a point. The device's own value wins.
                soc=to_float(payload.get("battSoc"), to_float(payload.get("emsSoc"))),
                soh=to_float(payload.get("battSoh"), to_float(payload.get("emsSoh"))),
                voltage=to_float(payload.get("battVolt"), to_float(payload.get("emsVoltage"))),
                current=to_float(payload.get("battCurr"), to_float(payload.get("emsCurrent"))),
                power=to_float(payload.get("bmsPower"), to_float(payload.get("emsPower"))),
                capacity_raw=to_float(payload.get("battCapacity")),
                capacity_unit="Ah",
                remaining_energy_kwh=to_float(
                    payload.get("remainingBatteryEnergy"),
                    to_float(payload.get("remainingBatteryEnergy1")),
                ),
                total_ems_capacity_kwh=to_float(payload.get("totalEmsCapacity")),
                charging_state=to_int(payload.get("bmsChargingState")),
                bms_state=to_str(payload.get("bmsState")),
                cell_voltage_max=_cell_voltage(payload.get("maxVoltage2bms")),
                cell_voltage_min=_cell_voltage(payload.get("minVoltage2bms")),
                cell_voltages=cell_voltages,
            ),
            thermal=ThermalReadings(
                battery_max_c=to_float(payload.get("tempMax")),
                battery_min_c=to_float(payload.get("tempMin")),
                device_max_c=to_float(payload.get("devTempMax")),
                device_min_c=to_float(payload.get("devTempMin")),
                cell_temperatures=cell_temps,
            ),
            totals=EnergyTotals(
                total_kwh=to_float(payload.get("totalEnergy")),
                total_unit=to_str(payload.get("totalEnergyUnit")),
                energy_today_kwh=to_float(payload.get("eLoadToday")),
                energy_total_kwh=to_float(
                    payload.get("eLoadTotal"),
                    to_float(payload.get("eLoadYear"), to_float(payload.get("tLoadYear"))),
                ),
            ),
            raw=dict(payload),
        )


def _float_tuple(value: Any) -> tuple[float, ...]:
    """Coerce a list-like payload field into a tuple of floats."""
    if not isinstance(value, (list, tuple)):
        return ()
    coerced = [to_float(item) for item in value]
    return tuple(item for item in coerced if item is not None)


def _cell_voltage(value: Any) -> float | None:
    """Normalise a cell voltage to volts.

    The vendor reports them in **millivolts** on some families (``3442``)
    and in **volts** on others (``3.331``). A value above 100 V is
    physically impossible for a lithium cell, so it is unambiguously
    millivolts.
    """
    number = to_float(value)
    if number is None:
        return None
    if abs(number) > 100:
        return number / 1000
    return number


def _parse_timestamp(raw_epoch: Any, raw_str: Any) -> datetime | None:
    """Build a timezone-aware timestamp from the epoch millis or the string."""
    millis = to_int(raw_epoch)
    if millis is not None and millis > 0:
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    text = to_str(raw_str)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
