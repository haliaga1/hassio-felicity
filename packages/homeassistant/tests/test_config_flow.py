"""Tests for the Felicity Solar config flow."""

from __future__ import annotations

import httpx
import pytest
import respx
from custom_components.felicity_solar.const import (
    CONF_API_NODE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    DOMAIN,
)
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import API_URL, envelope, load_fixture, plant_id


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_user_step_validates_the_credentials(hass: HomeAssistant) -> None:
    """A valid login moves the flow to the plant step."""
    respx.post(f"{API_URL}/userlogin").mock(
        return_value=httpx.Response(200, json=load_fixture("userlogin.json"))
    )
    respx.post(f"{API_URL}/plant/list_plant").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("list_plant.json")))
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "fixture@example.com",
            CONF_PASSWORD: "password",
            CONF_API_NODE: "INT",
        },
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "plant"
    assert result["errors"] == {}


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_invalid_credentials_show_an_error(hass: HomeAssistant) -> None:
    """A rejected login is reported without creating an entry."""
    respx.post(f"{API_URL}/userlogin").mock(
        return_value=httpx.Response(200, json=load_fixture("userlogin_error_credentials.json"))
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "fixture@example.com", CONF_PASSWORD: "wrong", CONF_API_NODE: "INT"},
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_a_single_plant_skips_the_plant_step(hass: HomeAssistant) -> None:
    """With one installation the flow creates the entry right away."""
    respx.post(f"{API_URL}/userlogin").mock(
        return_value=httpx.Response(200, json=load_fixture("userlogin.json"))
    )
    single = load_fixture("list_plant.json")
    single["dataList"] = single["dataList"][:1]
    single["total"] = 1
    respx.post(f"{API_URL}/plant/list_plant").mock(
        return_value=httpx.Response(200, json=envelope(single))
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "fixture@example.com", CONF_PASSWORD: "password", CONF_API_NODE: "INT"},
    )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PLANT_ID] == plant_id()


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_the_plant_step_selects_an_installation(hass: HomeAssistant) -> None:
    """The user picks one of the plants."""
    respx.post(f"{API_URL}/userlogin").mock(
        return_value=httpx.Response(200, json=load_fixture("userlogin.json"))
    )
    respx.post(f"{API_URL}/plant/list_plant").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("list_plant.json")))
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "fixture@example.com", CONF_PASSWORD: "password", CONF_API_NODE: "INT"},
    )
    second_plant = load_fixture("list_plant.json")["dataList"][1]["id"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PLANT_ID: second_plant}
    )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PLANT_ID] == second_plant
    assert result["title"]


@pytest.mark.usefixtures("enable_custom_integrations")
@respx.mock
async def test_an_already_configured_account_is_aborted(hass: HomeAssistant) -> None:
    """The same account cannot be added twice."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "fixture@example.com"},
        unique_id="fixture@example.com",
    ).add_to_hass(hass)

    respx.post(f"{API_URL}/userlogin").mock(
        return_value=httpx.Response(200, json=load_fixture("userlogin.json"))
    )
    respx.post(f"{API_URL}/plant/list_plant").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("list_plant.json")))
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "fixture@example.com", CONF_PASSWORD: "password", CONF_API_NODE: "INT"},
    )
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
