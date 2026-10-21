"""Contract tests: every endpoint against a recorded FSolar payload.

The fixtures were captured from a live IVEM8048-II installation and
redacted. They hold the **unwrapped** ``data`` payload, which is what the
service layer sees.

The expected values are **derived from the fixture itself** rather than
hardcoded, so re-capturing the fixtures (the plant produces different
numbers every minute) does not break the suite. What is asserted is the
*mapping*: that the right field ends up in the right attribute.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
import respx
from helpers import envelope, load_fixture

from felicity_client.auth import AuthService, StoredToken
from felicity_client.client import FelicityClient
from felicity_client.exceptions import (
    FelicityAPIError,
    FelicityAuthError,
    FelicityTokenExpiredError,
)
from felicity_client.http import FelicityHTTP
from felicity_client.models.common import ProductType

BASE_URL = "https://shine-api.felicitysolar.com"


def _route(path: str, fixture: str, *, raw: bool = False, method: str = "POST") -> respx.Route:
    """Register a route that answers with a recorded fixture."""
    payload = load_fixture(fixture)
    if not raw:
        payload = envelope(payload)
    factory = respx.get if method == "GET" else respx.post
    return factory(f"{BASE_URL}{path}").mock(return_value=httpx.Response(200, json=payload))


def _num(payload: dict[str, Any], key: str) -> float:
    """Read a numeric field of a raw payload."""
    value = payload.get(key)
    assert value is not None, f"the fixture has no {key}"
    return float(value)


@pytest.fixture
def client() -> FelicityClient:
    """A client with a valid, pre-seeded token."""
    instance = FelicityClient("fixture@example.com", "password")
    token = load_fixture("userlogin.json")["data"]["token"]
    instance.auth.restore(StoredToken(token=token, expires_at=4102444800.0))
    return instance


@pytest.fixture
def inverter_payload() -> dict[str, Any]:
    """The recorded inverter snapshot."""
    return load_fixture("snapshot_inverter.json")


@pytest.fixture
def battery_payload() -> dict[str, Any]:
    """The recorded battery snapshot."""
    return load_fixture("snapshot_battery.json")


class TestLogin:
    async def test_successful_login_returns_a_token(self) -> None:
        route = _route("/userlogin", "userlogin.json", raw=True)
        service = AuthService("fixture@example.com", "password")
        token = await service.get_token()
        assert route.called
        assert token.startswith("Bearer_")

    async def test_the_password_is_rsa_encrypted(self) -> None:
        route = _route("/userlogin", "userlogin.json", raw=True)
        service = AuthService("fixture@example.com", "password")
        await service.get_token()
        sent = json.loads(route.calls[0].request.content)
        assert sent["userName"] == "fixture@example.com"
        # The field is called "password" but must not carry the plaintext.
        assert sent["password"] != "password"
        assert len(base64.b64decode(sent["password"])) == 256

    async def test_bad_credentials_raise(self) -> None:
        _route("/userlogin", "userlogin_error_credentials.json", raw=True)
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
        rotated = _generate_public_key_b64()

        async def _refresh(self: Any) -> str:
            return rotated

        monkeypatch.setattr(AuthService, "_refresh_public_key", _refresh)
        service = AuthService("fixture@example.com", "password")
        token = await service.get_token()
        assert token.startswith("Bearer_")
        assert service.login_count == 1

    async def test_the_token_is_cached_between_calls(self) -> None:
        route = _route("/userlogin", "userlogin.json", raw=True)
        service = AuthService("fixture@example.com", "password")
        first = await service.get_token()
        second = await service.get_token()
        assert first == second
        assert route.call_count == 1


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


class TestPlants:
    async def test_lists_the_plants(self, client: FelicityClient) -> None:
        _route("/plant/list_plant", "list_plant.json")
        plants = await client.list_plants()
        assert len(plants) == 2
        assert plants[0].id
        assert plants[0].country_id == "245"

    async def test_gets_the_plant_details(self, client: FelicityClient) -> None:
        """The details endpoint needs plantId, not id."""
        payload = load_fixture("plant_details.json")
        _route("/plant/plantDetails", "plant_details.json")
        details = await client.get_plant_details(payload["id"])
        assert details.rated_power_kwp == pytest.approx(_num(payload, "ratedPower"))
        assert details.device_count == payload["deviceCount"]
        assert details.accumulated_pv_kwh == pytest.approx(_num(payload, "accPv"))

    async def test_the_plant_details_expose_the_daily_counters(
        self, client: FelicityClient
    ) -> None:
        """These counters are the only source of grid import and export."""
        payload = load_fixture("plant_details.json")
        _route("/plant/plantDetails", "plant_details.json")
        details = await client.get_plant_details(payload["id"])
        assert details.today_pv_kwh == pytest.approx(_num(payload, "todayPv"))
        assert details.today_load_kwh == pytest.approx(_num(payload, "todayLoad"))
        assert details.today_grid_input_kwh == pytest.approx(_num(payload, "todayGridInput"))
        assert details.today_feed_output_kwh == pytest.approx(_num(payload, "todayFeedOutput"))
        assert details.today_battery_charging_kwh == pytest.approx(
            _num(payload, "todayBatteryCharging")
        )
        assert details.today_battery_discharge_kwh == pytest.approx(
            _num(payload, "todayBatteryDischarge")
        )
        assert details.today_self_consumption_kwh == pytest.approx(_num(payload, "todayPvOwner"))
        assert details.month_pv_kwh == pytest.approx(_num(payload, "monthPv"))


class TestDevices:
    async def test_lists_every_device(self, client: FelicityClient) -> None:
        _route("/device/list_device_all_type", "list_device_all_type.json")
        devices = await client.list_devices()
        assert len(devices) == 4

    async def test_filters_by_plant(self, client: FelicityClient) -> None:
        _route("/device/list_device_all_type", "list_device_all_type.json")
        all_devices = await client.list_devices()
        plant_id = all_devices[0].plant_id
        devices = await client.list_devices(plant_id=plant_id)
        assert devices
        assert all(d.plant_id == plant_id for d in devices)

    async def test_derives_the_product_type_from_device_type(self, client: FelicityClient) -> None:
        """The device list has no productTypeEnum; deviceType is the hint.

        Without this, every device would be UNKNOWN and **no entity would
        be created at all**.
        """
        payload = load_fixture("list_device_all_type.json")
        _route("/device/list_device_all_type", "list_device_all_type.json")
        devices = await client.list_devices()
        by_sn = {d.serial_number: d for d in devices}
        for record in payload["dataList"]:
            device = by_sn[record["deviceSn"]]
            if record["deviceType"] == "OG":
                assert device.product_type is ProductType.INVERTER
            elif record["deviceType"] == "BP":
                assert device.product_type is ProductType.BATTERY

    async def test_reads_the_inverter_snapshot(
        self, client: FelicityClient, inverter_payload: dict[str, Any]
    ) -> None:
        _route("/device/get_device_snapshot", "snapshot_inverter.json")
        snapshot = await client.get_snapshot(inverter_payload["deviceSn"])
        assert snapshot.product_type is ProductType.INVERTER
        # pvTotalPower is the total of every PV string.
        assert snapshot.pv.power == pytest.approx(_num(inverter_payload, "pvTotalPower"))
        assert snapshot.pv.voltage == pytest.approx(_num(inverter_payload, "pvVolt"))
        assert snapshot.pv.energy_today_kwh == pytest.approx(_num(inverter_payload, "ePvToday"))
        assert snapshot.ac_out.power == pytest.approx(_num(inverter_payload, "acTotalOutActPower"))
        assert snapshot.ac_out.load_percent == pytest.approx(_num(inverter_payload, "loadPercent"))
        assert snapshot.battery.soc == pytest.approx(_num(inverter_payload, "emsSoc"))
        assert snapshot.thermal.device_max_c == pytest.approx(_num(inverter_payload, "devTempMax"))
        assert snapshot.totals.total_kwh == pytest.approx(_num(inverter_payload, "totalEnergy"))

    async def test_reads_the_battery_snapshot(
        self, client: FelicityClient, battery_payload: dict[str, Any]
    ) -> None:
        _route("/device/get_device_snapshot", "snapshot_battery.json")
        snapshot = await client.get_snapshot(battery_payload["deviceSn"])
        assert snapshot.product_type is ProductType.BATTERY
        assert snapshot.battery.soc == pytest.approx(_num(battery_payload, "battSoc"))
        assert snapshot.battery.soh == pytest.approx(_num(battery_payload, "battSoh"))
        assert snapshot.battery.voltage == pytest.approx(_num(battery_payload, "battVolt"))
        assert snapshot.battery.current == pytest.approx(_num(battery_payload, "battCurr"))
        assert snapshot.battery.power == pytest.approx(_num(battery_payload, "bmsPower"))
        assert snapshot.battery.charging_state == int(battery_payload["bmsChargingState"])
        assert snapshot.battery.charging_state_name == "charging"
        assert snapshot.battery.remaining_energy_kwh == pytest.approx(
            _num(battery_payload, "remainingBatteryEnergy")
        )

    async def test_the_cell_voltages_are_normalised_to_volts(
        self, client: FelicityClient, battery_payload: dict[str, Any]
    ) -> None:
        """The vendor reports them in millivolts on this family."""
        _route("/device/get_device_snapshot", "snapshot_battery.json")
        snapshot = await client.get_snapshot(battery_payload["deviceSn"])
        assert snapshot.battery.cell_voltage_max == pytest.approx(
            _num(battery_payload, "maxVoltage2bms") / 1000
        )
        assert snapshot.battery.cell_voltage_min == pytest.approx(
            _num(battery_payload, "minVoltage2bms") / 1000
        )

    async def test_an_empty_snapshot_is_an_error(self, client: FelicityClient) -> None:
        respx.post(f"{BASE_URL}/device/get_device_snapshot").mock(
            return_value=httpx.Response(200, json=envelope({}))
        )
        with pytest.raises(ValueError, match="empty snapshot"):
            await client.get_snapshot("UNKNOWN")


class TestEnergyFlow:
    async def test_reads_the_flow(self, client: FelicityClient) -> None:
        """The field names are confirmed against the live API."""
        payload = load_fixture("get_energy_flow2.json")
        _route("/device/get_energy_flow2", "get_energy_flow2.json", method="GET")
        flow = await client.get_energy_flow(payload["deviceSn"], payload["plantId"])
        assert flow.pv_power == pytest.approx(_num(payload, "pvTotalPower"))
        assert flow.load_power == pytest.approx(_num(payload, "acTotalOutActPower"))
        assert flow.battery_power == pytest.approx(_num(payload, "emsPower"))
        assert flow.grid_power == pytest.approx(_num(payload, "meterPower"))
        assert flow.generator_power == pytest.approx(_num(payload, "genPower"))


class TestAlerts:
    async def test_the_request_carries_the_pagination_and_dates(
        self, client: FelicityClient
    ) -> None:
        """The endpoint requires a page and a date range, or it fails."""
        route = _route("/device/device_warring_list", "device_warring_list.json")
        alerts = await client.list_alerts()
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body["pageNum"] == 1
        assert body["pageSize"] == 50
        assert body["leftDate"].count(":") == 2, "the dates need a full timestamp"
        assert isinstance(alerts, list)


class TestTokenExpiry:
    async def test_a_302_to_token_expiration_triggers_a_relogin(self) -> None:
        """The gateway signals an expired token with a redirect, not a 401."""
        respx.post(f"{BASE_URL}/device/list_device_all_type").mock(
            side_effect=[
                httpx.Response(302, headers={"location": f"{BASE_URL}/token_expiration"}),
                httpx.Response(200, json=load_fixture("list_device_all_type.json")),
            ]
        )
        login_route = _route("/userlogin", "userlogin.json", raw=True)

        service = AuthService("fixture@example.com", "password")
        http = FelicityHTTP(auth=service)
        async with http:
            await http.post("/device/list_device_all_type", json={})
        assert login_route.called, "the client should have re-authenticated"

    async def test_a_persistent_302_raises(self, client: FelicityClient) -> None:
        respx.post(f"{BASE_URL}/device/list_device_all_type").mock(
            return_value=httpx.Response(302, headers={"location": "/token_expiration"})
        )
        _route("/userlogin", "userlogin.json", raw=True)
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
