"""Contract tests: every endpoint against a recorded FSolar payload.

These tests are the tripwire for upstream drift. When the vendor changes a
field name or the shape of a response, the matching test fails and the
fixture has to be re-captured.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
import respx
from helpers import load_fixture

from felicity_client.auth import AuthService, StoredToken
from felicity_client.client import FelicityClient
from felicity_client.crypto import public_key_fingerprint
from felicity_client.exceptions import (
    FelicityAPIError,
    FelicityAuthError,
    FelicityTokenExpiredError,
)
from felicity_client.http import FelicityHTTP
from felicity_client.models.common import ProductType

BASE_URL = "https://shine-api.felicitysolar.com"


def _json_route(path: str, fixture: str) -> respx.Route:
    """Register a route that answers with a recorded fixture."""
    return respx.post(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json=load_fixture(fixture))
    )


@pytest.fixture
def client() -> FelicityClient:
    """A client with a valid, pre-seeded token."""
    instance = FelicityClient("fixture@example.com", "password")
    token = load_fixture("userlogin.json")["data"]["token"]
    instance.auth.restore(StoredToken(token=token, expires_at=4102444800.0))
    return instance


def _generate_public_key_b64() -> str:
    """Generate a throwaway 2048-bit RSA public key in SPKI base64 form."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


class TestLogin:
    async def test_successful_login_returns_a_token(self) -> None:
        route = _json_route("/userlogin", "userlogin.json")
        service = AuthService("fixture@example.com", "password")
        token = await service.get_token()
        assert route.called
        assert token.startswith("Bearer_")

    async def test_the_password_is_rsa_encrypted(self) -> None:
        route = _json_route("/userlogin", "userlogin.json")
        service = AuthService("fixture@example.com", "password")
        await service.get_token()
        sent = json.loads(route.calls[0].request.content)
        assert sent["userName"] == "fixture@example.com"
        # The field is called "password" but must not carry the plaintext.
        assert sent["password"] != "password"
        assert len(base64.b64decode(sent["password"])) == 256

    async def test_bad_credentials_raise(self) -> None:
        _json_route("/userlogin", "userlogin_error_credentials.json")
        service = AuthService("fixture@example.com", "wrong")
        with pytest.raises(FelicityAuthError) as excinfo:
            await service.get_token()
        assert "10010001" in str(excinfo.value)

    async def test_an_rsa_error_triggers_a_key_refresh(self, monkeypatch: Any) -> None:
        """When the backend rejects the ciphertext, the key is re-extracted."""
        respx.post(f"{BASE_URL}/userlogin").mock(
            side_effect=[
                httpx.Response(200, json=load_fixture("userlogin_error_rsa.json")),
                httpx.Response(200, json=load_fixture("userlogin.json")),
            ]
        )
        # A genuinely different key, as if the vendor had rotated it.
        rotated = _generate_public_key_b64()

        async def _refresh(self: Any) -> str:
            return rotated

        monkeypatch.setattr(AuthService, "_refresh_public_key", _refresh)
        service = AuthService("fixture@example.com", "password")
        token = await service.get_token()
        assert token.startswith("Bearer_")
        assert service.login_count == 1
        assert service.public_key_fingerprint == public_key_fingerprint(rotated)

    async def test_the_token_is_cached_between_calls(self) -> None:
        route = _json_route("/userlogin", "userlogin.json")
        service = AuthService("fixture@example.com", "password")
        first = await service.get_token()
        second = await service.get_token()
        assert first == second
        assert route.call_count == 1


class TestPlants:
    async def test_lists_the_plants(self, client: FelicityClient) -> None:
        _json_route("/plant/list_plant", "list_plant.json")
        plants = await client.list_plants()
        assert len(plants) == 2
        assert plants[0].id == "plant-0001"
        assert plants[0].name == "Casa Principal"
        assert plants[0].country_id == "CL"

    async def test_gets_the_plant_details(self, client: FelicityClient) -> None:
        _json_route("/plant/plantDetails", "plant_details.json")
        plant = await client.get_plant("plant-0001")
        assert plant.id == "plant-0001"
        assert plant.name == "Casa Principal"


class TestDevices:
    async def test_lists_every_device(self, client: FelicityClient) -> None:
        _json_route("/device/list_device_all_type", "list_device_all_type.json")
        devices = await client.list_devices()
        assert len(devices) == 4
        assert {d.serial_number for d in devices} == {
            "INV0001",
            "BAT0001",
            "CTL0001",
            "INV0002",
        }

    async def test_filters_by_plant(self, client: FelicityClient) -> None:
        _json_route("/device/list_device_all_type", "list_device_all_type.json")
        devices = await client.list_devices(plant_id="plant-0001")
        assert len(devices) == 3
        assert all(d.plant_id == "plant-0001" for d in devices)

    async def test_reads_the_product_type(self, client: FelicityClient) -> None:
        _json_route("/device/list_device_all_type", "list_device_all_type.json")
        devices = await client.list_devices()
        by_sn = {d.serial_number: d for d in devices}
        assert by_sn["INV0001"].product_type is ProductType.INVERTER
        assert by_sn["BAT0001"].product_type is ProductType.BATTERY
        assert by_sn["CTL0001"].product_type is ProductType.CONTROLLER

    async def test_reads_the_inverter_snapshot(self, client: FelicityClient) -> None:
        _json_route("/device/get_device_snapshot", "snapshot_inverter.json")
        snapshot = await client.get_snapshot("INV0001")
        assert snapshot.device_sn == "INV0001"
        assert snapshot.product_type is ProductType.INVERTER
        assert snapshot.pv.power == pytest.approx(2943.8)
        assert snapshot.pv.voltage == pytest.approx(312.5)
        assert snapshot.pv.energy_today_kwh == pytest.approx(12.48)
        assert snapshot.ac_in.voltage == pytest.approx(231.4)
        assert snapshot.ac_in.frequency == pytest.approx(50.01)
        assert snapshot.ac_out.power == pytest.approx(1204.5)
        assert snapshot.battery.soc == pytest.approx(87.0)
        assert snapshot.battery.soh == pytest.approx(99.0)
        assert snapshot.thermal.device_max_c == pytest.approx(45.6)
        assert snapshot.thermal.battery_max_c == pytest.approx(31.2)
        assert snapshot.totals.total_kwh == pytest.approx(3842.15)

    async def test_reads_the_battery_snapshot(self, client: FelicityClient) -> None:
        _json_route("/device/get_device_snapshot", "snapshot_battery.json")
        snapshot = await client.get_snapshot("BAT0001")
        assert snapshot.product_type is ProductType.BATTERY
        assert snapshot.battery.soc == pytest.approx(87.0)
        assert snapshot.battery.capacity_kwh == pytest.approx(5.12)
        assert snapshot.battery.remaining_energy_kwh == pytest.approx(4.454)
        assert snapshot.battery.charging_state == 1
        assert snapshot.battery.charging_state_name == "charging"
        assert len(snapshot.battery.cell_voltages) == 4

    async def test_reads_the_controller_snapshot(self, client: FelicityClient) -> None:
        _json_route("/device/get_device_snapshot", "snapshot_controller.json")
        snapshot = await client.get_snapshot("CTL0001")
        assert snapshot.product_type is ProductType.CONTROLLER
        assert snapshot.work_mode == "Standby"

    async def test_an_empty_snapshot_is_an_error(self, client: FelicityClient) -> None:
        respx.post(f"{BASE_URL}/device/get_device_snapshot").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": {}, "message": "ok"})
        )
        with pytest.raises(ValueError, match="empty snapshot"):
            await client.get_snapshot("UNKNOWN")

    async def test_a_missing_device_raises_not_found(self, client: FelicityClient) -> None:
        _json_route("/device/list_device_all_type", "list_device_all_type.json")
        with pytest.raises(ValueError, match="not registered"):
            await client.get_device("NOPE")


class TestEnergyFlow:
    async def test_reads_the_flow(self, client: FelicityClient) -> None:
        respx.get(f"{BASE_URL}/device/get_energy_flow2").mock(
            return_value=httpx.Response(200, json=load_fixture("get_energy_flow2.json"))
        )
        flow = await client.get_energy_flow("INV0001", "plant-0001")
        assert flow.device_sn == "INV0001"
        assert flow.plant_id == "plant-0001"
        assert flow.pv_power == pytest.approx(2943.8)
        assert flow.load_power == pytest.approx(1204.5)
        assert flow.battery_power == pytest.approx(-658.5)
        assert flow.grid_power == pytest.approx(1204.5)
        assert flow.value("loadPercent") == pytest.approx(48.0)


class TestAlerts:
    async def test_lists_the_alerts(self, client: FelicityClient) -> None:
        _json_route("/device/device_warring_list", "device_warring_list.json")
        alerts = await client.list_alerts()
        assert len(alerts) == 1
        assert alerts[0].id == "warn-9001"
        assert alerts[0].device_sn == "BAT0001"
        assert alerts[0].title == "LowCellVoltage"
        assert alerts[0].severity == "2"
        assert alerts[0].is_active is True


class TestTokenExpiry:
    async def test_a_302_to_token_expiration_triggers_a_relogin(self) -> None:
        """The gateway signals an expired token with a redirect, not a 401."""
        respx.post(f"{BASE_URL}/device/list_device_all_type").mock(
            side_effect=[
                httpx.Response(302, headers={"location": f"{BASE_URL}/token_expiration"}),
                httpx.Response(200, json=load_fixture("list_device_all_type.json")),
            ]
        )
        login_route = _json_route("/userlogin", "userlogin.json")

        service = AuthService("fixture@example.com", "password")
        http = FelicityHTTP(auth=service)
        async with http:
            data = await http.post("/device/list_device_all_type", json={})
        assert data is not None
        assert login_route.called, "the client should have re-authenticated"

    async def test_a_persistent_302_raises(self, client: FelicityClient) -> None:
        """Even after a re-login, a 302 to /token_expiration is fatal."""
        respx.post(f"{BASE_URL}/device/list_device_all_type").mock(
            return_value=httpx.Response(302, headers={"location": "/token_expiration"})
        )
        _json_route("/userlogin", "userlogin.json")
        http = FelicityHTTP(auth=client.auth)
        async with http:
            with pytest.raises(FelicityTokenExpiredError):
                await http.post("/device/list_device_all_type", json={})


class TestEnvelope:
    async def test_a_non_200_code_raises(self, client: FelicityClient) -> None:
        respx.post(f"{BASE_URL}/plant/list_plant").mock(
            return_value=httpx.Response(200, json={"code": 10010001, "message": "nope", "data": ""})
        )
        with pytest.raises(FelicityAPIError) as excinfo:
            await client.list_plants()
        assert excinfo.value.code == 10010001
        assert excinfo.value.message == "nope"
