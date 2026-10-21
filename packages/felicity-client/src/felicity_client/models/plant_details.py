"""Plant details, including the plant level energy counters.

``POST /plant/plantDetails`` is the richest endpoint of the API. Besides
the installation metadata it exposes the **daily energy counters** of the
plant, which the device snapshot does not have:

============================  ======================================
Counter                       Meaning
============================  ======================================
``todayPv``                   photovoltaic production today
``todayLoad``                 consumption today
``todayInput`` / ``todayOut`` energy in / out of the plant today
``todayGridInput``            energy imported from the grid today
``todayFeedOutput``           energy exported to the grid today
``todayBatteryCharging``      energy stored in the battery today
``todayBatteryDischarge``     energy taken from the battery today
``todayTotalConsum``          total consumption today
``todayPvOwner``              self consumption today
``accPv`` / ``yearPv``        accumulated photovoltaic production
``monthPv``                   production this month
============================  ======================================

The daily counters reset at the plant's local midnight, so they are
reported with ``state_class=TOTAL`` and a ``last_reset`` in Home
Assistant. ``accPv`` only grows and is the right source for the Energy
Dashboard.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .._coerce import to_float, to_int, to_str

__all__ = ["PlantDetails"]


@dataclass(frozen=True, slots=True)
class PlantDetails:
    """The details and the energy counters of a plant."""

    id: str
    name: str | None = None
    address: str | None = None
    country_name: str | None = None
    business_time_zone: str | None = None
    installer: str | None = None
    electricity_price: float | None = None
    currency: str | None = None
    rated_power_kwp: float | None = None
    device_count: int | None = None
    online_device_count: int | None = None
    inverter_count: int | None = None
    battery_count: int | None = None
    controller_count: int | None = None
    pv_power_w: float | None = None

    # --- Daily counters (reset every day) ---
    today_pv_kwh: float | None = None
    today_load_kwh: float | None = None
    today_input_kwh: float | None = None
    today_output_kwh: float | None = None
    today_grid_input_kwh: float | None = None
    today_feed_output_kwh: float | None = None
    today_battery_charging_kwh: float | None = None
    today_battery_discharge_kwh: float | None = None
    today_total_consumption_kwh: float | None = None
    today_self_consumption_kwh: float | None = None

    # --- Accumulated counters ---
    accumulated_pv_kwh: float | None = None
    year_pv_kwh: float | None = None
    month_pv_kwh: float | None = None

    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PlantDetails:
        """Build the details from a ``/plant/plantDetails`` payload."""
        return cls(
            id=to_str(payload.get("id")) or "",
            name=to_str(payload.get("plantName")),
            address=to_str(payload.get("address")),
            country_name=to_str(payload.get("countryName")),
            business_time_zone=to_str(payload.get("businessTimeZone")),
            installer=to_str(payload.get("installer")),
            electricity_price=to_float(payload.get("electricityPrice")),
            currency=to_str(payload.get("currency")),
            rated_power_kwp=to_float(payload.get("ratedPower")),
            device_count=to_int(payload.get("deviceCount")),
            online_device_count=to_int(payload.get("onlineDeviceCount")),
            inverter_count=to_int(payload.get("invCount")),
            battery_count=to_int(payload.get("bpCount")),
            controller_count=to_int(payload.get("coCount")),
            pv_power_w=to_float(payload.get("pvTotalPower")),
            today_pv_kwh=to_float(payload.get("todayPv")),
            today_load_kwh=to_float(payload.get("todayLoad")),
            today_input_kwh=to_float(payload.get("todayInput")),
            today_output_kwh=to_float(payload.get("todayOut")),
            today_grid_input_kwh=to_float(payload.get("todayGridInput")),
            today_feed_output_kwh=to_float(payload.get("todayFeedOutput")),
            today_battery_charging_kwh=to_float(payload.get("todayBatteryCharging")),
            today_battery_discharge_kwh=to_float(payload.get("todayBatteryDischarge")),
            today_total_consumption_kwh=to_float(payload.get("todayTotalConsum")),
            today_self_consumption_kwh=to_float(payload.get("todayPvOwner")),
            accumulated_pv_kwh=to_float(payload.get("accPv"), to_float(payload.get("yearPv"))),
            year_pv_kwh=to_float(payload.get("yearPv")),
            month_pv_kwh=to_float(payload.get("monthPv")),
            raw=dict(payload),
        )
