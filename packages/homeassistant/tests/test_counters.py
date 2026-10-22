"""Tests for the lifetime counters accumulated from the daily ones.

The FSolar API publishes daily counters for the grid and the battery, but
the Home Assistant Energy Dashboard needs lifetime ones. The counters are
accumulated from the day-to-day delta of the daily values.

The battery is the exception: the vendor publishes its daily counter empty,
so its energy is integrated from the power of the flow.
"""

from __future__ import annotations

from datetime import date

import pytest
from custom_components.felicity_solar.counters import LifetimeCounters
from custom_components.felicity_solar.vendor.felicity_client.models.energy import (
    EnergyFlow,
)
from custom_components.felicity_solar.vendor.felicity_client.models.plant_details import (
    PlantDetails,
)


def _details(**kwargs: float) -> PlantDetails:
    """Build a plant details payload with the given daily counters."""
    payload = {
        "id": "plant-1",
        "todayGridInput": "0",
        "todayFeedOutput": "0",
        "todayBatteryCharging": "0",
        "todayBatteryDischarge": "0",
    }
    for key, value in kwargs.items():
        payload[key] = str(value)
    return PlantDetails.from_payload(payload)


def _flow(battery_power: float | None) -> EnergyFlow:
    """Build an energy flow with the given battery power."""
    return EnergyFlow(device_sn="sn-1", plant_id="plant-1", battery_power=battery_power)


class TestLifetimeCounters:
    def test_the_first_read_counts_the_whole_daily_value(self) -> None:
        counters = LifetimeCounters()
        counters.update(_details(todayGridInput=5.0))
        assert counters.grid_import_kwh == pytest.approx(5.0)

    def test_the_delta_of_the_same_day_is_added(self) -> None:
        counters = LifetimeCounters()
        counters.update(_details(todayGridInput=5.0))
        counters.update(_details(todayGridInput=8.0))
        assert counters.grid_import_kwh == pytest.approx(8.0)

    def test_a_day_rollover_does_not_lose_the_energy(self) -> None:
        """The daily counter resets at midnight; the total must not."""
        counters = LifetimeCounters()
        counters.update(_details(todayGridInput=5.0))
        # Pretend the last read was yesterday.
        counters._day = "2000-01-01"
        counters.update(_details(todayGridInput=2.0))
        assert counters.grid_import_kwh == pytest.approx(7.0)

    def test_a_counter_that_goes_backwards_does_not_reduce_the_total(self) -> None:
        counters = LifetimeCounters()
        counters.update(_details(todayGridInput=5.0))
        counters.update(_details(todayGridInput=3.0))
        assert counters.grid_import_kwh == pytest.approx(5.0)

    def test_every_counter_is_tracked(self) -> None:
        counters = LifetimeCounters()
        counters.update(
            _details(
                todayGridInput=1.0,
                todayFeedOutput=2.0,
                todayBatteryCharging=3.0,
                todayBatteryDischarge=4.0,
            )
        )
        assert counters.grid_import_kwh == pytest.approx(1.0)
        assert counters.grid_export_kwh == pytest.approx(2.0)
        assert counters.battery_charging_kwh == pytest.approx(3.0)
        assert counters.battery_discharging_kwh == pytest.approx(4.0)

    def test_a_missing_daily_counter_is_skipped(self) -> None:
        counters = LifetimeCounters()
        counters.update(_details())
        counters.update(_details(todayGridInput=4.0))
        assert counters.grid_import_kwh == pytest.approx(4.0)

    def test_the_counters_survive_a_round_trip(self) -> None:
        counters = LifetimeCounters()
        counters.update(_details(todayGridInput=5.0, todayFeedOutput=1.5))
        restored = LifetimeCounters.from_dict(counters.to_dict())
        assert restored.grid_import_kwh == pytest.approx(5.0)
        assert restored.grid_export_kwh == pytest.approx(1.5)
        # The restored counter knows the daily value, so it does not count
        # it a second time.
        restored.update(_details(todayGridInput=6.0))
        assert restored.grid_import_kwh == pytest.approx(6.0)

    def test_the_day_is_today(self) -> None:
        counters = LifetimeCounters()
        counters.update(_details(todayGridInput=1.0))
        assert counters._day == date.today().isoformat()


class TestBatteryFromTheFlow:
    """The daily counter of the battery comes empty from the API."""

    def test_the_energy_is_integrated_from_the_power(self) -> None:
        counters = LifetimeCounters()
        counters.update_flow(_flow(1000.0), 0.5)
        assert counters.battery_charging_kwh == pytest.approx(0.5)
        assert counters.battery_discharging_kwh == pytest.approx(0.0)

    def test_a_discharging_battery_is_counted_as_discharged(self) -> None:
        counters = LifetimeCounters()
        counters.update_flow(_flow(-1000.0), 0.5)
        assert counters.battery_discharging_kwh == pytest.approx(0.5)
        assert counters.battery_charging_kwh == pytest.approx(0.0)

    def test_without_elapsed_time_nothing_is_counted(self) -> None:
        counters = LifetimeCounters()
        counters.update_flow(_flow(1000.0), 0.0)
        assert counters.battery_charging_kwh == pytest.approx(0.0)

    def test_without_a_flow_nothing_is_counted(self) -> None:
        counters = LifetimeCounters()
        counters.update_flow(None, 1.0)
        assert counters.battery_charging_kwh == pytest.approx(0.0)

    def test_without_a_power_nothing_is_counted(self) -> None:
        counters = LifetimeCounters()
        counters.update_flow(_flow(None), 1.0)
        assert counters.battery_charging_kwh == pytest.approx(0.0)

    def test_the_energy_accumulates_over_the_updates(self) -> None:
        counters = LifetimeCounters()
        counters.update_flow(_flow(1000.0), 0.5)
        counters.update_flow(_flow(2000.0), 0.5)
        assert counters.battery_charging_kwh == pytest.approx(1.5)

    def test_the_history_of_the_battery_is_seeded_once(self) -> None:
        counters = LifetimeCounters()
        counters.seed_battery(10.0, 2.0)
        assert counters.battery_charging_kwh == pytest.approx(10.0)
        assert counters.battery_discharging_kwh == pytest.approx(2.0)
        # A second seed does not change anything.
        counters.seed_battery(20.0, 5.0)
        assert counters.battery_charging_kwh == pytest.approx(10.0)
        assert counters.battery_discharging_kwh == pytest.approx(2.0)

    def test_the_seed_survives_a_round_trip(self) -> None:
        counters = LifetimeCounters()
        counters.seed_battery(10.0, 2.0)
        restored = LifetimeCounters.from_dict(counters.to_dict())
        assert restored.seeded is True
        restored.seed_battery(20.0, 5.0)
        assert restored.battery_charging_kwh == pytest.approx(10.0)

    def test_the_energy_of_the_day_is_measured_from_the_lifetime(self) -> None:
        counters = LifetimeCounters()
        counters.seed_battery(10.0, 2.0)
        counters.update_flow(_flow(1000.0), 1.0)
        assert counters.battery_charging_today_kwh == pytest.approx(1.0)
        assert counters.battery_discharging_today_kwh == pytest.approx(0.0)

    def test_a_new_day_starts_the_counter_again(self) -> None:
        counters = LifetimeCounters()
        counters.seed_battery(10.0, 2.0)
        counters.update_flow(_flow(1000.0), 1.0)
        assert counters.battery_charging_today_kwh == pytest.approx(1.0)
        # Pretend the last read was yesterday.
        counters._day = "2000-01-01"
        counters.update(_details())
        assert counters.battery_charging_today_kwh == pytest.approx(0.0)
        counters.update_flow(_flow(1000.0), 1.0)
        assert counters.battery_charging_today_kwh == pytest.approx(1.0)
