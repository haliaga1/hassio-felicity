"""Shared fixtures for the Felicity Solar Home Assistant tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from custom_components.felicity_solar.const import (
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
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
if not FIXTURE_DIR.exists():
    FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

API_URL = "https://shine-api.felicitysolar.com"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by file name."""
    path = FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing fixture: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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
            CONF_PLANT_ID: "plant-0001",
            CONF_PLANT_NAME: "Casa Principal",
            CONF_API_NODE: "INT",
            CONF_DEVICE_SERIALS: [],
            CONF_SCAN_DEVICES: True,
            CONF_SCAN_INTERVAL: 60,
        },
        unique_id="fixture@example.com",
    )


@pytest.fixture
def hass_fixture(hass: HomeAssistant) -> HomeAssistant:
    """Expose the Home Assistant instance."""
    return hass
