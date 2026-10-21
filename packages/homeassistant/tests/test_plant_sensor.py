"""Tests for the plant level energy flow sensors."""

from __future__ import annotations

import pytest
import respx
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_sensor import _register_routes


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_sensors_report_the_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The plant sensors expose the four flows of the installation."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.casa_principal_plant_pv_power")
    assert state is not None
    assert float(state.state) == pytest.approx(2943.8)
    assert state.attributes["unit_of_measurement"] == UnitOfPower.WATT
    assert state.attributes["device_class"] == SensorDeviceClass.POWER
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_sensors_state_the_sign_is_unverified(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The sign convention of the backend is not confirmed, and it is said so."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.casa_principal_plant_grid_power")
    assert state is not None
    assert state.attributes["sign_verified"] is False
    assert state.attributes["plant_id"] == "plant-0001"


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_sensors_can_be_disabled(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The plant flow can be turned off from the options."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options={"enable_plant_flow": False})
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.casa_principal_plant_pv_power") is None


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_battery_flow_keeps_its_sign(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A discharging battery reports a negative power, as the vendor sends it."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.casa_principal_plant_battery_power")
    assert state is not None
    assert float(state.state) == pytest.approx(-658.5)
