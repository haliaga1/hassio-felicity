"""Lifetime energy counters built from the daily ones of the plant.

The FSolar API exposes **daily** counters for the grid and the battery
(``todayGridInput``, ``todayFeedOutput``, ``todayBatteryCharging``,
``todayBatteryDischarge``) and a **lifetime** one only for the
photovoltaic production (``accPv``).

The Home Assistant Energy Dashboard needs lifetime counters
(``state_class: total_increasing``) for every panel. This module turns the
daily counters into lifetime ones by accumulating their day-to-day delta.

The accumulation is exact rather than a Riemann sum of the power: it uses
the vendor's own kWh counters. Its only weakness is the obvious one — a day
the integration was not running is lost, because the daily counter rolled
over while nobody was reading it.

The battery is the exception: the vendor publishes its daily counter empty
(``todayBatteryCharging`` is always ``0``), so its energy is integrated from
the power of the flow instead.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .vendor.felicity_client.models.energy import EnergyFlow
from .vendor.felicity_client.models.plant_details import PlantDetails

_LOGGER = logging.getLogger(__name__)

__all__ = ["LifetimeCounters"]

#: The longest stretch of time the integration integrates in one go. A
#: longer gap means the instance was not running, and the energy of that
#: time is lost rather than guessed.
MAX_INTEGRATION_HOURS = 0.25


@dataclass
class LifetimeCounters:
    """The accumulated energy of a plant, in kWh.

    The counters only ever grow, which is what ``total_increasing`` means.
    """

    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    battery_charging_kwh: float = 0.0
    battery_discharging_kwh: float = 0.0
    #: The daily values seen on the last refresh, used to compute the delta.
    _last_daily: dict[str, float] = field(default_factory=dict)
    #: The day the daily counters belonged to.
    _day: str = ""
    #: Whether the battery energy was already read from the power series.
    seeded: bool = False
    #: The lifetime counters when the day started, to get the daily ones.
    _day_start: dict[str, float] = field(default_factory=dict)

    def update(self, details: PlantDetails) -> None:
        """Accumulate the daily counters of the plant.

        A counter that went **down** means the day rolled over: the whole
        current value is then new energy.
        """
        daily = {
            "grid_import": details.today_grid_input_kwh,
            "grid_export": details.today_feed_output_kwh,
            "battery_charging": details.today_battery_charging_kwh,
            "battery_discharging": details.today_battery_discharge_kwh,
        }
        today = date.today().isoformat()

        rolled_over = self._day != today
        self._day = today

        for key, value in daily.items():
            if value is None:
                continue
            previous = self._last_daily.get(key)
            if previous is None or rolled_over:
                delta = value
            else:
                delta = value - previous
                if delta < 0:
                    # The vendor corrected the counter downwards; do not
                    # let the lifetime total go backwards.
                    delta = 0.0
            setattr(self, _ATTRIBUTES[key], getattr(self, _ATTRIBUTES[key]) + delta)
            self._last_daily[key] = value

        if rolled_over or not self._day_start:
            # El dia nuevo, o la primera vez tras una actualizacion que no
            # guardaba el inicio del dia.
            self._roll_day()

    def _roll_day(self) -> None:
        """Remember the counters of the day that just started."""
        self._day_start = {
            "battery_charging": self.battery_charging_kwh,
            "battery_discharging": self.battery_discharging_kwh,
        }

    @property
    def battery_charging_today_kwh(self) -> float:
        """The energy the battery has charged since the day started."""
        return max(
            0.0,
            self.battery_charging_kwh - self._day_start.get("battery_charging", 0.0),
        )

    @property
    def battery_discharging_today_kwh(self) -> float:
        """The energy the battery has discharged since the day started."""
        return max(
            0.0,
            self.battery_discharging_kwh - self._day_start.get("battery_discharging", 0.0),
        )

    def update_flow(self, flow: EnergyFlow | None, hours: float) -> None:
        """Accumulate the energy the battery has charged or discharged.

        The daily counter the API publishes for the battery comes empty, so
        its energy is integrated from the power of the flow: a positive
        battery power means the battery is charging, a negative one means it
        is discharging.
        """
        if flow is None or hours <= 0:
            return
        if self._day != date.today().isoformat():
            self._day = date.today().isoformat()
            self._roll_day()
        power = flow.battery_power
        if power is None:
            return
        if power >= 0:
            self.battery_charging_kwh += power * hours / 1000
        else:
            self.battery_discharging_kwh += -power * hours / 1000

    def seed_battery(self, charging_kwh: float, discharging_kwh: float) -> None:
        """Adopt the energy the battery has already moved.

        The vendor publishes the daily counter of the battery empty, so the
        energy it moved before the integration started is read from the
        power series of the API. It is only done once: afterwards the
        counter grows with the power of the flow.
        """
        if self.seeded:
            return
        self.battery_charging_kwh = max(self.battery_charging_kwh, charging_kwh)
        self.battery_discharging_kwh = max(self.battery_discharging_kwh, discharging_kwh)
        self.seeded = True

    def to_dict(self) -> dict[str, Any]:
        """Serialise the counters for storage."""
        return {
            "grid_import_kwh": self.grid_import_kwh,
            "grid_export_kwh": self.grid_export_kwh,
            "battery_charging_kwh": self.battery_charging_kwh,
            "battery_discharging_kwh": self.battery_discharging_kwh,
            "last_daily": dict(self._last_daily),
            "day": self._day,
            "seeded": self.seeded,
            "day_start": dict(self._day_start),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifetimeCounters:
        """Rebuild the counters from storage."""
        counters = cls()
        counters.grid_import_kwh = float(payload.get("grid_import_kwh", 0.0))
        counters.grid_export_kwh = float(payload.get("grid_export_kwh", 0.0))
        counters.battery_charging_kwh = float(payload.get("battery_charging_kwh", 0.0))
        counters.battery_discharging_kwh = float(payload.get("battery_discharging_kwh", 0.0))
        last_daily = payload.get("last_daily")
        if isinstance(last_daily, Mapping):
            counters._last_daily = {
                str(k): float(v) for k, v in last_daily.items() if isinstance(v, (int, float))
            }
        counters._day = str(payload.get("day", ""))
        counters.seeded = bool(payload.get("seeded", False))
        day_start = payload.get("day_start")
        if isinstance(day_start, Mapping):
            counters._day_start = {
                str(key): float(value)
                for key, value in day_start.items()
                if isinstance(value, (int, float))
            }
        return counters


#: The daily counter of the plant -> the attribute of the lifetime counter.
_ATTRIBUTES: dict[str, str] = {
    "grid_import": "grid_import_kwh",
    "grid_export": "grid_export_kwh",
    "battery_charging": "battery_charging_kwh",
    "battery_discharging": "battery_discharging_kwh",
}
