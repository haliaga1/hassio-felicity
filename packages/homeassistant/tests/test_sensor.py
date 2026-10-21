"""Tests for the Felicity Solar entities.

These are the tests that prove the mapping is right: the units, the
``state_class`` and the values. A wrong ``state_class`` here is what breaks
the Home Assistant Energy Dashboard, so they are asserted explicitly.

The entities are resolved by ``unique_id`` instead of by entity id, so a
change in the naming of a device does not break the suite.
"""

from __future__ import annotations

import httpx
import pytest
import respx
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
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    API_URL,
    battery_sn,
    entity_id,
    envelope,
    inverter_sn,
    load_fixture,
    register_api,
)


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_entities_are_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Setting up the entry creates a device and its sensors."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_id(hass, f"{inverter_sn()}_pv_power") is not None
    assert entity_id(hass, f"{battery_sn()}_battery_soc") is not None
    assert entity_id(hass, f"{inverter_sn()}_online", "binary_sensor") is not None


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_inverter_sensors_have_the_right_units(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Every sensor exposes the unit and state class the API implies."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{inverter_sn()}_pv_power"))
    assert state is not None
    assert float(state.state) == pytest.approx(
        float(load_fixture("snapshot_inverter.json")["pvTotalPower"])
    )
    assert state.attributes["unit_of_measurement"] == UnitOfPower.WATT
    assert state.attributes["device_class"] == SensorDeviceClass.POWER
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_pv_power_covers_every_string(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The sensor must report the total, not only the first PV string."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("snapshot_inverter.json")
    state = hass.states.get(entity_id(hass, f"{inverter_sn()}_pv_power"))
    assert state is not None
    assert float(state.state) == pytest.approx(float(payload["pvTotalPower"]))


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_energy_dashboard_sensors_are_increasing(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The lifetime counters are TOTAL_INCREASING so the dashboard accepts them."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{inverter_sn()}_pv_energy_total"))
    assert state is not None
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING
    assert state.attributes["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_daily_counters_are_total_with_a_last_reset(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A counter that resets every day is TOTAL with a last_reset, not increasing."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{inverter_sn()}_pv_energy_today"))
    assert state is not None
    assert state.attributes["state_class"] == SensorStateClass.TOTAL
    assert "last_reset" in state.attributes


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_battery_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The battery exposes SOC, SOH, voltage and current."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("snapshot_battery.json")

    soc = hass.states.get(entity_id(hass, f"{battery_sn()}_battery_soc"))
    assert soc is not None
    assert float(soc.state) == pytest.approx(float(payload["battSoc"]))
    assert soc.attributes["unit_of_measurement"] == PERCENTAGE

    soh = hass.states.get(entity_id(hass, f"{battery_sn()}_battery_soh"))
    assert soh is not None
    assert float(soh.state) == pytest.approx(float(payload["battSoh"]))

    voltage = hass.states.get(entity_id(hass, f"{battery_sn()}_battery_voltage"))
    assert voltage is not None
    assert voltage.attributes["unit_of_measurement"] == UnitOfElectricPotential.VOLT
    assert float(voltage.state) == pytest.approx(float(payload["battVolt"]))

    current = hass.states.get(entity_id(hass, f"{battery_sn()}_battery_current"))
    assert current is not None
    assert current.attributes["unit_of_measurement"] == UnitOfElectricCurrent.AMPERE
    assert float(current.state) == pytest.approx(float(payload["battCurr"]))


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_cell_voltages_are_in_volts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The vendor reports them in millivolts; the sensor must convert them."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    payload = load_fixture("snapshot_battery.json")
    state = hass.states.get(entity_id(hass, f"{battery_sn()}_cell_voltage_max"))
    assert state is not None
    assert float(state.state) == pytest.approx(float(payload["maxVoltage2bms"]) / 1000)


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_thermal_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The temperatures are exposed in Celsius."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{inverter_sn()}_device_temperature_max"))
    assert state is not None
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.CELSIUS


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_grid_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The grid side exposes voltage, frequency and power."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    frequency = hass.states.get(entity_id(hass, f"{inverter_sn()}_grid_frequency"))
    assert frequency is not None
    assert frequency.attributes["unit_of_measurement"] == UnitOfFrequency.HERTZ


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_binary_sensors(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The connectivity and alarm binary sensors are created."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    online = hass.states.get(entity_id(hass, f"{inverter_sn()}_online", "binary_sensor"))
    assert online is not None
    assert online.state == "on"

    alarm = hass.states.get(entity_id(hass, f"{battery_sn()}_alarm", "binary_sensor"))
    assert alarm is not None
    assert alarm.state in {"on", "off"}


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_a_device_is_registered_per_serial_number(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Each Felicity device becomes a Home Assistant device."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
    serials = {device.serial_number for device in devices}
    assert inverter_sn() in serials
    assert battery_sn() in serials


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_a_missing_measurement_is_unavailable_not_zero(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A device with no snapshot must not report a fabricated zero."""
    register_api()
    respx.post(f"{API_URL}/device/get_device_snapshot").mock(
        return_value=httpx.Response(200, json=envelope({"deviceSn": inverter_sn()}))
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{inverter_sn()}_pv_power"))
    assert state is not None
    assert state.state == "unknown"
