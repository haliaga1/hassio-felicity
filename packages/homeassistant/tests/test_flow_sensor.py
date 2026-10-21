"""Tests for the flow state sensors.

The flow sensors answer the question the Energy Dashboard does not: *which
way* is the energy going. A positive battery power means charging, a
positive grid power means importing, and anything within the dead band is
"at rest".
"""

from __future__ import annotations

import httpx
import pytest
import respx
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import API_URL, entity_id, plant_id, register_api


def _flow_payload(grid: float, pv: float, battery: float) -> dict:
    """Build an energy flow payload with the given powers."""
    return {
        "code": 200,
        "data": {
            "deviceSn": "DEV1",
            "plantId": "plant-0001",
            "pvTotalPower": str(pv),
            "acTotalOutActPower": "100",
            "emsPower": str(battery),
            "meterPower": str(grid),
            "acTtlInPower": str(grid),
            "batteryCharging": "0",
            "batteryDischarge": "0",
            "genPower": "0",
            "smartTotalPower": "0",
        },
        "message": "success",
    }


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_flow_sensors_exist(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Each plant exposes the state of its three flows."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    for key in ("plant_grid_flow", "plant_pv_flow", "plant_battery_flow"):
        state = hass.states.get(entity_id(hass, f"{plant_id()}_{key}"))
        assert state is not None, key
        assert state.attributes["device_class"] == SensorDeviceClass.ENUM
        assert state.state in {
            "reposo",
            "importando",
            "exportando",
            "produciendo",
            "cargando",
            "descargando",
        }


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_flow_states_follow_the_sign(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A positive power means charging or importing, a negative one the opposite."""
    register_api()
    respx.get(f"{API_URL}/device/get_energy_flow2").mock(
        return_value=httpx.Response(200, json=_flow_payload(grid=500.0, pv=1000.0, battery=250.0))
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    grid = hass.states.get(entity_id(hass, f"{plant_id()}_plant_grid_flow"))
    pv = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_flow"))
    battery = hass.states.get(entity_id(hass, f"{plant_id()}_plant_battery_flow"))

    assert grid is not None and grid.state == "importando"
    assert pv is not None and pv.state == "produciendo"
    assert battery is not None and battery.state == "cargando"


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_flow_states_invert_with_the_sign(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Exporting and discharging are the opposite states."""
    register_api()
    respx.get(f"{API_URL}/device/get_energy_flow2").mock(
        return_value=httpx.Response(200, json=_flow_payload(grid=-500.0, pv=0.0, battery=-250.0))
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    grid = hass.states.get(entity_id(hass, f"{plant_id()}_plant_grid_flow"))
    pv = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_flow"))
    battery = hass.states.get(entity_id(hass, f"{plant_id()}_plant_battery_flow"))

    assert grid is not None and grid.state == "exportando"
    assert pv is not None and pv.state == "reposo"
    assert battery is not None and battery.state == "descargando"


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_a_flow_at_rest_is_idle(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A battery at 100 % with no power is "at rest", not charging."""
    register_api()
    respx.get(f"{API_URL}/device/get_energy_flow2").mock(
        return_value=httpx.Response(200, json=_flow_payload(grid=0.0, pv=0.0, battery=0.0))
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    for key in ("plant_grid_flow", "plant_pv_flow", "plant_battery_flow"):
        state = hass.states.get(entity_id(hass, f"{plant_id()}_{key}"))
        assert state is not None, key
        assert state.state == "reposo"
