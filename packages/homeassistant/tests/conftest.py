"""Shared fixtures and helpers for the Felicity Solar Home Assistant tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

# Home Assistant discovers custom integrations by importing the
# ``custom_components`` package, so the repository root has to be importable.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.felicity_solar.const import (  # noqa: E402
    CONF_API_NODE,
    CONF_DEVICE_SERIALS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    CONF_SCAN_DEVICES,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

API_URL = "https://shine-api.felicitysolar.com"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by file name."""
    path = FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing fixture: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def envelope(data: Any, code: int = 200, message: str = "success") -> dict[str, Any]:
    """Wrap a payload in the FSolar response envelope."""
    return {"code": code, "data": data, "message": message}


def inverter_sn() -> str:
    """The serial number of the recorded inverter."""
    for record in load_fixture("list_device_all_type.json")["dataList"]:
        if record.get("deviceType") == "OG":
            return str(record["deviceSn"])
    raise LookupError("the fixture has no inverter")


def battery_sn() -> str:
    """The serial number of the recorded battery."""
    for record in load_fixture("list_device_all_type.json")["dataList"]:
        if record.get("deviceType") == "BP":
            return str(record["deviceSn"])
    raise LookupError("the fixture has no battery")


def plant_id() -> str:
    """The identifier of the recorded plant."""
    return str(load_fixture("list_plant.json")["dataList"][0]["id"])


def entity_id(hass: HomeAssistant, unique_id: str, domain: str = "sensor") -> str | None:
    """Resolve an entity id from its unique id."""
    registry = er.async_get(hass)
    return registry.async_get_entity_id(domain, DOMAIN, unique_id)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the custom integration in every test."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A config entry for a Felicity Solar account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Casa Principal",
        data={
            CONF_EMAIL: "fixture@example.com",
            CONF_PASSWORD: "password",
            CONF_PLANT_ID: plant_id(),
            CONF_PLANT_NAME: "Casa Principal",
            CONF_API_NODE: "INT",
            CONF_DEVICE_SERIALS: [],
            CONF_SCAN_DEVICES: True,
            CONF_SCAN_INTERVAL: 60,
        },
        unique_id="fixture@example.com",
    )


def register_api() -> None:
    """Register the FSolar endpoints used during a refresh."""
    respx.post(f"{API_URL}/userlogin").mock(
        return_value=httpx.Response(200, json=load_fixture("userlogin.json"))
    )
    respx.post(f"{API_URL}/device/list_device_all_type").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("list_device_all_type.json")))
    )
    respx.post(f"{API_URL}/device/get_device_snapshot").mock(side_effect=_snapshot_response)
    respx.get(f"{API_URL}/device/get_energy_flow2").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("get_energy_flow2.json")))
    )
    respx.post(f"{API_URL}/plant/plantDetails").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("plant_details.json")))
    )
    respx.post(f"{API_URL}/plant/list_plant").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("list_plant.json")))
    )
    respx.post(f"{API_URL}/device/device_warring_list").mock(
        return_value=httpx.Response(200, json=envelope(load_fixture("device_warring_list.json")))
    )
    respx.post(f"{API_URL}/storageRealtimeData/chart_storageRealtimeData_mate").mock(
        return_value=httpx.Response(
            200, json=envelope(load_fixture("chart_storageRealtimeData_mate.json"))
        )
    )


def _snapshot_response(request: httpx.Request) -> httpx.Response:
    """Answer with the snapshot of the requested device."""
    payload = json.loads(request.content)
    serial_number = payload.get("deviceSn")
    if serial_number == inverter_sn():
        data = load_fixture("snapshot_inverter.json")
    elif serial_number == battery_sn():
        data = load_fixture("snapshot_battery.json")
    else:
        data = load_fixture("snapshot_controller.json")
    return httpx.Response(200, json=envelope(data))
