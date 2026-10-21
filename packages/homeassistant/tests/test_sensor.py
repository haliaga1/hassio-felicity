"""Tests for the Felicity Solar entities.

These are the tests that prove the mapping is right: the units, the
``state_class`` and the values. A wrong ``state_class`` here is what breaks
the Home Assistant Energy Dashboard, so they are asserted explicitly.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from custom_components.felicity_solar.const import DOMAIN
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import API_URL, load_fixture


def _register_routes() -> None:
    """Register the FSolar endpoints used during a refresh."""
    respx.post(f"{API_URL}/userlogin").mock(
        return_value=httpx.Response(200, json=load_fixture("userlogin.json"))
    )
    respx.post(f"{API_URL}/device/list_device_all_type").mock(
        return_value=httpx.Response(200, json=load_fixture("list_device_all_type.json"))
    )
    respx.post(f"{API_URL}/device/get_device_snapshot").mock(
        side_effect=lambda request: _snapshot_for(request)
    )
    respx.get(f"{API_URL}/device/get_energy_flow2").mock(
        return_value=httpx.Response(200, json=load_fixture("get_energy_flow2.json"))
    )
    respx.post(f"{API_URL}/device/device_warring_list").mock(
        return_value=httpx.Response(200, json=load_fixture("device_warring_list.json"))
    )


def _snapshot_for(request: httpx.Request) -> httpx.Response:
    """Answer with the snapshot of the requested device."""
    import json

    payload = json.loads(request.content)
    serial_number = payload.get("deviceSn")
    mapping = {
        "INV0001": "snapshot_inverter.json",
        "BAT0001": "snapshot_battery.json",
        "CTL0001": "snapshot_controller.json",
    }
    fixture = mapping.get(serial_number, "snapshot_inverter.json")
    return httpx.Response(200, json=load_fixture(fixture))


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_entities_are_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Setting up the entry creates a device and its sensors."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
    assert entities, "no entity was created"

    # The inverter contributes the PV sensors.
    pv_power = registry.async_get_entity_id("sensor", DOMAIN, "INV0001_pv_power")
    assert pv_power is not None


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_inverter_sensors_have_the_right_units(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Every sensor exposes the unit and state class the API implies."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.inversor_principal_pv_power")
    assert state is not None
    assert state.state == "2943.8"
    assert state.attributes["unit_of_measurement"] == UnitOfPower.WATT
    assert state.attributes["device_class"] == SensorDeviceClass.POWER
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_energy_dashboard_sensors_are_increasing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The lifetime counters are TOTAL_INCREASING so the dashboard accepts them."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.inversor_principal_pv_energy_total")
    assert state is not None
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING
    assert state.attributes["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR
    assert float(state.state) == pytest.approx(1842.66)


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_daily_counters_are_not_increasing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A counter that resets every day is TOTAL with a last_reset, not increasing."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.inversor_principal_pv_energy_today")
    assert state is not None
    assert state.attributes["state_class"] == SensorStateClass.TOTAL
    assert float(state.state) == pytest.approx(12.48)
    # A TOTAL sensor must tell Home Assistant when the counter was reset.
    assert "last_reset" in state.attributes


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_battery_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The battery exposes SOC, SOH, voltage and current."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    soc = hass.states.get("sensor.bateria_1_battery_state_of_charge")
    assert soc is not None
    assert float(soc.state) == pytest.approx(87.0)
    assert soc.attributes["unit_of_measurement"] == PERCENTAGE

    soh = hass.states.get("sensor.bateria_1_battery_state_of_health")
    assert soh is not None
    assert float(soh.state) == pytest.approx(99.0)

    voltage = hass.states.get("sensor.bateria_1_battery_voltage")
    assert voltage is not None
    assert voltage.attributes["unit_of_measurement"] == UnitOfElectricPotential.VOLT
    assert float(voltage.state) == pytest.approx(53.05)

    current = hass.states.get("sensor.bateria_1_battery_current")
    assert current is not None
    assert current.attributes["unit_of_measurement"] == UnitOfElectricCurrent.AMPERE
    assert float(current.state) == pytest.approx(-12.55)


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_thermal_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The temperatures are exposed in Celsius."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.inversor_principal_maximum_device_temperature")
    assert state is not None
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.CELSIUS
    assert float(state.state) == pytest.approx(45.6)


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_grid_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The grid side exposes voltage, frequency and power."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    frequency = hass.states.get("sensor.inversor_principal_grid_frequency")
    assert frequency is not None
    assert frequency.attributes["unit_of_measurement"] == UnitOfFrequency.HERTZ
    assert float(frequency.state) == pytest.approx(50.01)


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_binary_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The connectivity and alarm binary sensors are created."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    online = hass.states.get("binary_sensor.inversor_principal_online")
    assert online is not None
    assert online.state == "on"

    alarm = hass.states.get("binary_sensor.bateria_1_alarm")
    assert alarm is not None
    assert alarm.state == "on"
    assert alarm.attributes["alert_count"] == 1


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_a_device_is_registered_per_serial_number(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Each Felicity device becomes a Home Assistant device."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
    serials = {device.serial_number for device in devices}
    assert {"INV0001", "BAT0001", "CTL0001"} <= serials


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_controller_exposes_its_work_mode(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The controller exposes a non numeric attribute."""
    _register_routes()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.controlador_work_mode")
    assert state is not None
    assert state.state == "Standby"


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_a_missing_measurement_is_unavailable_not_zero(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A device with no snapshot must not report a fabricated zero."""
    _register_routes()
    respx.post(f"{API_URL}/device/get_device_snapshot").mock(
        return_value=httpx.Response(
            200, json={"code": 200, "data": {"deviceSn": "INV0001"}, "message": "ok"}
        )
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.inversor_principal_pv_power")
    assert state is not None
    assert state.state == "unknown"
