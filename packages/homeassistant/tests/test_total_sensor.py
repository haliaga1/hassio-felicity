"""Tests for the sensors that aggregate every configured plant.

Home Assistant has a single Energy Dashboard for the whole instance, so the
totals of several plants have to be summed into one entity.
"""

from __future__ import annotations

import pytest
import respx
from custom_components.felicity_solar.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    DOMAIN,
)
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import entity_id, load_fixture, register_api


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_aggregate_sums_the_plants(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The aggregate adds up the value of every plant."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, "felicity_solar_total_pv_energy"))
    assert state is not None
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING
    assert state.attributes["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR

    # A single plant is configured, so the aggregate is that plant's value.
    payload = load_fixture("plant_details.json")
    assert float(state.state) == pytest.approx(float(payload["accPv"]))
    assert state.attributes["plant_count"] == 1


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_aggregate_is_created_only_once(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Two entries of the same domain must not create the aggregate twice."""
    register_api()
    mock_config_entry.add_to_hass(hass)

    second = MockConfigEntry(
        domain=DOMAIN,
        title="Antupirén",
        data={
            CONF_EMAIL: "fixture@example.com",
            CONF_PASSWORD: "password",
            CONF_PLANT_ID: "plant-0002",
            CONF_PLANT_NAME: "Antupirén",
        },
        unique_id="fixture@example.com:plant-0002",
    )
    second.add_to_hass(hass)

    for entry in (mock_config_entry, second):
        if entry.state is not ConfigEntryState.LOADED:
            await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.LOADED

    state = hass.states.get(entity_id(hass, "felicity_solar_total_pv_energy"))
    assert state is not None
    assert state.attributes["plant_count"] == 2
    # The aggregate is a single entity, not one per entry.
    assert entity_id(hass, "felicity_solar_total_pv_power") is not None


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_aggregate_lists_every_plant(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The attributes show the contribution of each plant."""
    register_api()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id(hass, "felicity_solar_total_pv_energy"))
    assert state is not None
    payload = load_fixture("plant_details.json")
    assert payload["plantName"] in state.attributes
