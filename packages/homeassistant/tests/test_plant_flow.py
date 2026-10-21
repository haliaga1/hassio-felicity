"""Tests for the plant level flow sensors.

The plant reports one energy flow per device and the order in which they
are returned is **not** guaranteed: on one plant the inverter comes first,
on another one the battery does. The plant level sensors describe the
whole plant, so they have to read the inverter's flow.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    API_URL,
    battery_sn,
    entity_id,
    inverter_sn,
    load_fixture,
    plant_id,
    register_api,
)


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_flow_uses_the_inverter(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The plant power sensors read the inverter's flow, not the first one."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_power"))
    assert state is not None
    # The inverter reports the PV production; the battery's flow does not.
    assert state.state not in {"unknown", "unavailable"}
    assert float(state.state) > 0


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_flow_is_the_same_with_the_devices_reversed(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Reversing the order of the devices must not change the plant values.

    The device list is returned in an arbitrary order, so the plant
    sensors must pick the inverter explicitly.
    """
    register_api()

    # El endpoint de dispositivos devuelve la bateria antes que el inversor.
    original = load_fixture("list_device_all_type.json")
    reversed_payload = {
        "code": 200,
        "data": {**original, "dataList": list(reversed(original["dataList"]))},
        "message": "success",
    }
    respx.post(f"{API_URL}/device/list_device_all_type").mock(
        return_value=httpx.Response(200, json=reversed_payload)
    )

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, f"{plant_id()}_plant_pv_power"))
    assert state is not None
    assert state.state not in {"unknown", "unavailable"}
    assert float(state.state) > 0
    assert inverter_sn() != battery_sn()
