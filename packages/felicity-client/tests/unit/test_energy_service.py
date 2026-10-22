"""Tests for the energy service of the FSolar client."""

from __future__ import annotations

import httpx
import pytest
import respx

from felicity_client.http import FelicityHTTP
from felicity_client.services.energy import EnergyService, series_energy

API_URL = "https://shine-api.felicitysolar.com"


class _StubAuth:
    """An authentication service that hands out a fixed token."""

    async def get_token(self) -> str:
        """Return a bearer token."""
        return "Bearer_token"


@respx.mock
async def test_the_power_series_is_read() -> None:
    """The chart endpoint answers with one list of samples per field."""
    respx.post(f"{API_URL}/storageRealtimeData/chart_storageRealtimeData_mate").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "storageMateDTOS": [
                        {"field": "batteryCharging", "data": [1000, 2000, None]},
                        {"field": "batteryDischarge", "data": [0, -500, -500]},
                    ]
                },
            },
        )
    )
    async with FelicityHTTP(base_url=API_URL, timeout=10) as http:
        http.set_auth(_StubAuth())
        series = await EnergyService(http).get_storage_series("plant-1")
    assert series == {
        "batteryCharging": [1000.0, 2000.0, 0.0],
        "batteryDischarge": [0.0, -500.0, -500.0],
    }


def test_the_energy_of_a_series_is_integrated() -> None:
    """Five minute samples of a thousand watts are an eighth of a kWh."""
    assert series_energy([1000.0]) == pytest.approx(1000.0 * 5 / 60 / 1000)


def test_only_the_positive_samples_are_counted() -> None:
    """A battery that discharges reports a negative power."""
    assert series_energy([-1000.0, 1000.0], -1) == pytest.approx(1000.0 * 5 / 60 / 1000)
    assert series_energy([-1000.0, 1000.0]) == pytest.approx(1000.0 * 5 / 60 / 1000)
