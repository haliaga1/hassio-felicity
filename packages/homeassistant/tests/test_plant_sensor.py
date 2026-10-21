"""Tests for the plant level energy sensors.

The plant counters come from ``/plant/plantDetails``, the only endpoint
that exposes the daily grid import and export counters and the accumulated
photovoltaic production.
"""

from __future__ import annotations

import pytest
import respx
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import entity_id, load_fixture, plant_id, register_api


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_accumulated_pv_is_increasing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """This is the sensor the Energy Dashboard consumes."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("plant_details.json")
    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_energy_total"))
    assert state is not None
    assert float(state.state) == pytest.approx(float(payload["accPv"]))
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING
    assert state.attributes["device_class"] == SensorDeviceClass.ENERGY
    assert state.attributes["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_grid_counters_are_daily(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The grid import and export counters reset every day."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("plant_details.json")
    for key, field in (
        ("plant_grid_import_today", "todayGridInput"),
        ("plant_grid_export_today", "todayFeedOutput"),
        ("plant_battery_charging_today", "todayBatteryCharging"),
        ("plant_battery_discharge_today", "todayBatteryDischarge"),
    ):
        state = hass.states.get(entity_id(hass, f"{plant_id()}_{key}"))
        assert state is not None, key
        assert float(state.state) == pytest.approx(float(payload[field]))
        assert state.attributes["state_class"] == SensorStateClass.TOTAL
        assert "last_reset" in state.attributes


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_daily_pv_counter(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("plant_details.json")
    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_energy_today"))
    assert state is not None
    assert float(state.state) == pytest.approx(float(payload["todayPv"]))
    assert state.attributes["state_class"] == SensorStateClass.TOTAL


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_rated_power(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("plant_details.json")
    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_rated_power"))
    assert state is not None
    assert float(state.state) == pytest.approx(float(payload["ratedPower"]))
    assert state.attributes["unit_of_measurement"] == UnitOfPower.KILO_WATT


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_attributes(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The plant metadata travels with the sensor."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("plant_details.json")
    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_energy_total"))
    assert state is not None
    assert state.attributes["plant_id"] == plant_id()
    assert state.attributes["device_count"] == payload["deviceCount"]
    assert state.attributes["online_device_count"] == payload["onlineDeviceCount"]


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_flow_sensors(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The instantaneous flows of the plant."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("get_energy_flow2.json")
    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_power"))
    assert state is not None
    assert float(state.state) == pytest.approx(float(payload["pvTotalPower"]))
    assert state.attributes["unit_of_measurement"] == UnitOfPower.WATT
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_sensors_state_the_sign_is_unverified(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The sign convention of the flow is documented but not guaranteed."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_grid_power"))
    assert state is not None
    assert state.attributes["sign_verified"] is False
    assert state.attributes["plant_id"] == plant_id()


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_flow_can_be_disabled(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The instantaneous flow can be turned off from the options."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={"enable_plant_flow": False})
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_id(hass, f"{plant_id()}_plant_pv_power") is None
    # The energy counters are always available.
    assert entity_id(hass, f"{plant_id()}_plant_pv_energy_total") is not None
