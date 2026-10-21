"""Unit tests for the model layer: parsing, coercion and null handling.

The expectations are derived from the recorded fixtures, so re-capturing
them does not break the suite.
"""

from __future__ import annotations

from typing import Any

import pytest
from helpers import load_fixture

from felicity_client.models.alerts import Alert, AlertGroup
from felicity_client.models.common import Device, Plant, ProductType
from felicity_client.models.energy import EnergyFlow
from felicity_client.models.plant_details import PlantDetails
from felicity_client.models.snapshot import Snapshot


def _num(payload: dict[str, Any], key: str) -> float:
    """Read a numeric field of a raw payload."""
    value = payload.get(key)
    assert value is not None, f"the fixture has no {key}"
    return float(value)


class TestProductType:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("HIGH_FREQUENCY_INVERTER", ProductType.INVERTER),
            ("LITHIUM_BATTERY_PACK", ProductType.BATTERY),
            ("CONTROLLER", ProductType.CONTROLLER),
        ],
    )
    def test_parses_the_known_types(self, raw: str, expected: ProductType) -> None:
        assert ProductType.parse(raw) is expected

    @pytest.mark.parametrize("raw", [None, "", "SOMETHING_NEW", 42])
    def test_falls_back_to_unknown(self, raw: object) -> None:
        assert ProductType.parse(raw) is ProductType.UNKNOWN

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("BP", ProductType.BATTERY),
            ("OG", ProductType.INVERTER),
            ("PCS", ProductType.CONTROLLER),
            ("bp", ProductType.BATTERY),
        ],
    )
    def test_derives_the_type_from_the_device_type(self, raw: str, expected: ProductType) -> None:
        assert ProductType.from_device_type(raw) is expected

    @pytest.mark.parametrize("raw", [None, "", "XX"])
    def test_an_unknown_device_type_is_unknown(self, raw: object) -> None:
        assert ProductType.from_device_type(raw) is ProductType.UNKNOWN


class TestPlant:
    def test_parses_the_payload(self) -> None:
        record = load_fixture("list_plant.json")["dataList"][0]
        plant = Plant.from_payload(record)
        assert plant.id == record["id"]
        assert plant.name == record["plantName"]
        assert plant.country_id == "245"

    def test_tolerates_a_missing_id(self) -> None:
        plant = Plant.from_payload({"plantName": "Sin id"})
        assert plant.id == ""
        assert plant.name == "Sin id"


class TestPlantDetails:
    def test_parses_the_counters(self) -> None:
        payload = load_fixture("plant_details.json")
        details = PlantDetails.from_payload(payload)
        assert details.id == payload["id"]
        assert details.rated_power_kwp == pytest.approx(_num(payload, "ratedPower"))
        assert details.device_count == payload["deviceCount"]
        assert details.today_pv_kwh == pytest.approx(_num(payload, "todayPv"))
        assert details.accumulated_pv_kwh == pytest.approx(_num(payload, "accPv"))
        assert details.month_pv_kwh == pytest.approx(_num(payload, "monthPv"))

    def test_a_missing_counter_is_none(self) -> None:
        details = PlantDetails.from_payload({"id": "x"})
        assert details.today_pv_kwh is None
        assert details.accumulated_pv_kwh is None


class TestDevice:
    def test_parses_the_payload(self) -> None:
        record = load_fixture("list_device_all_type.json")["dataList"][0]
        device = Device.from_payload(record)
        assert device.serial_number == record["deviceSn"]
        assert device.model == record["deviceModel"]
        assert device.plant_id == record["plantId"]
        assert device.alias == record["alias"]
        assert device.type_code == int(record["typeCode"])

    def test_derives_the_product_type(self) -> None:
        records = load_fixture("list_device_all_type.json")["dataList"]
        for record in records:
            device = Device.from_payload(record)
            assert device.product_type is not ProductType.UNKNOWN, record

    def test_the_friendly_name_falls_back_to_the_model(self) -> None:
        """A device with no alias has the serial number there; that makes
        for a terrible entity id, so the model is used instead."""
        record = load_fixture("list_device_all_type.json")["dataList"][0]
        device = Device.from_payload(record)
        assert device.friendly_name != device.serial_number
        assert device.friendly_name == (device.alias or device.model)

    def test_the_friendly_name_keeps_a_real_alias(self) -> None:
        device = Device.from_payload({"deviceSn": "X", "alias": "Inversor"})
        assert device.friendly_name == "Inversor"

    def test_reports_offline(self) -> None:
        assert Device.from_payload({"deviceSn": "X", "status": "offline"}).is_online is False

    def test_the_normal_status_means_online(self) -> None:
        """The live API reports a healthy device as ``NM``."""
        assert Device.from_payload({"deviceSn": "X", "status": "NM"}).is_online is True

    def test_reports_unknown_status_as_none(self) -> None:
        assert Device.from_payload({"deviceSn": "X", "status": "weird"}).is_online is None
        assert Device.from_payload({"deviceSn": "X"}).is_online is None


class TestSnapshot:
    def test_parses_the_inverter(
        self,
    ) -> None:
        payload = load_fixture("snapshot_inverter.json")
        snapshot = Snapshot.from_payload(payload)
        assert snapshot.device_sn == payload["deviceSn"]
        assert snapshot.pv.power == pytest.approx(_num(payload, "pvTotalPower"))
        assert snapshot.pv.energy_today_kwh == pytest.approx(_num(payload, "ePvToday"))
        assert snapshot.ac_out.power == pytest.approx(_num(payload, "acTotalOutActPower"))
        assert snapshot.battery.soc == pytest.approx(_num(payload, "emsSoc"))
        assert snapshot.thermal.device_max_c == pytest.approx(_num(payload, "devTempMax"))
        assert snapshot.totals.total_kwh == pytest.approx(_num(payload, "totalEnergy"))
        assert snapshot.wifi_signal is None or isinstance(snapshot.wifi_signal, int)

    def test_the_pv_total_covers_every_string(self) -> None:
        """``pvPower`` is only the first string; the total is what matters."""
        payload = load_fixture("snapshot_inverter.json")
        snapshot = Snapshot.from_payload(payload)
        if "pv2Power" in payload:
            assert snapshot.pv.power == pytest.approx(_num(payload, "pvTotalPower"))
            assert snapshot.pv.power != pytest.approx(_num(payload, "pvPower"))

    def test_parses_the_battery(self) -> None:
        payload = load_fixture("snapshot_battery.json")
        snapshot = Snapshot.from_payload(payload)
        assert snapshot.product_type is ProductType.BATTERY
        assert snapshot.battery.soc == pytest.approx(_num(payload, "battSoc"))
        assert snapshot.battery.soh == pytest.approx(_num(payload, "battSoh"))
        assert snapshot.battery.voltage == pytest.approx(_num(payload, "battVolt"))
        assert snapshot.battery.current == pytest.approx(_num(payload, "battCurr"))
        assert snapshot.battery.power == pytest.approx(_num(payload, "bmsPower"))
        assert snapshot.battery.remaining_energy_kwh == pytest.approx(
            _num(payload, "remainingBatteryEnergy")
        )

    def test_the_charging_state_is_read(self) -> None:
        payload = load_fixture("snapshot_battery.json")
        snapshot = Snapshot.from_payload(payload)
        assert snapshot.battery.charging_state == int(payload["bmsChargingState"])
        # The live battery was charging while the snapshot was taken.
        assert snapshot.battery.charging_state_name == "charging"
        assert snapshot.battery.power > 0

    def test_missing_fields_become_none_not_zero(self) -> None:
        """The critical rule: a missing value is never a fabricated zero."""
        snapshot = Snapshot.from_payload(
            {"deviceSn": "X", "productTypeEnum": "HIGH_FREQUENCY_INVERTER"}
        )
        assert snapshot.pv.power is None
        assert snapshot.battery.soc is None
        assert snapshot.thermal.device_max_c is None
        assert snapshot.totals.total_kwh is None

    def test_null_fields_become_none(self) -> None:
        snapshot = Snapshot.from_payload(
            {
                "deviceSn": "X",
                "productTypeEnum": "LITHIUM_BATTERY_PACK",
                "pvPower": None,
                "battSoc": "null",
                "ePvTotal": "",
            }
        )
        assert snapshot.pv.power is None
        assert snapshot.battery.soc is None
        assert snapshot.pv.energy_total_kwh is None

    def test_falls_back_to_the_ems_soc(self) -> None:
        """Some inverter payloads only carry the EMS values."""
        snapshot = Snapshot.from_payload(
            {
                "deviceSn": "X",
                "productTypeEnum": "HIGH_FREQUENCY_INVERTER",
                "emsSoc": "55",
                "emsVoltage": "52.1",
            }
        )
        assert snapshot.battery.soc == pytest.approx(55.0)
        assert snapshot.battery.voltage == pytest.approx(52.1)

    def test_a_zero_state_of_health_means_not_reported(self) -> None:
        """A device without a state of health sensor reports 0, which would
        otherwise show up as an impossible "0 % health"."""
        snapshot = Snapshot.from_payload(
            {"deviceSn": "X", "productTypeEnum": "HIGH_FREQUENCY_INVERTER", "emsSoh": "0"}
        )
        assert snapshot.battery.soh is None

    def test_a_real_state_of_health_is_kept(self) -> None:
        snapshot = Snapshot.from_payload(
            {"deviceSn": "X", "productTypeEnum": "LITHIUM_BATTERY_PACK", "battSoh": "100"}
        )
        assert snapshot.battery.soh == pytest.approx(100.0)

    def test_parses_the_timestamp(self) -> None:
        payload = load_fixture("snapshot_inverter.json")
        snapshot = Snapshot.from_payload(payload)
        assert snapshot.timestamp is not None
        assert snapshot.timestamp.year == 2026

    def test_an_unknown_product_type_is_not_fatal(self) -> None:
        snapshot = Snapshot.from_payload({"deviceSn": "X", "productTypeEnum": "NEW_THING"})
        assert snapshot.product_type is ProductType.UNKNOWN
        assert snapshot.device_sn == "X"


class TestEnergyFlow:
    def test_parses_the_payload(self) -> None:
        payload = load_fixture("get_energy_flow2.json")
        flow = EnergyFlow.from_payload(payload)
        assert flow.device_sn == payload["deviceSn"]
        assert flow.plant_id == payload["plantId"]
        assert flow.pv_power == pytest.approx(_num(payload, "pvTotalPower"))
        assert flow.load_power == pytest.approx(_num(payload, "acTotalOutActPower"))
        assert flow.battery_power == pytest.approx(_num(payload, "emsPower"))
        assert flow.grid_power == pytest.approx(_num(payload, "meterPower"))

    def test_the_load_is_not_the_smart_load(self) -> None:
        """A naive token match would pick smartLoadTotalPower (always 0)."""
        payload = load_fixture("get_energy_flow2.json")
        flow = EnergyFlow.from_payload(payload)
        if "smartLoadTotalPower" in payload:
            assert flow.load_power == pytest.approx(_num(payload, "acTotalOutActPower"))
            assert flow.load_power != pytest.approx(_num(payload, "smartLoadTotalPower"))

    def test_ignores_identifier_fields(self) -> None:
        flow = EnergyFlow.from_payload(
            {"deviceSn": "X", "time": "2026-01-01", "status": "online", "pvPower": "10"}
        )
        assert flow.pv_power == pytest.approx(10.0)
        assert "status" not in flow.values
        assert "deviceSn" not in flow.values

    def test_an_empty_payload_yields_no_values(self) -> None:
        flow = EnergyFlow.from_payload({})
        assert flow.values == {}
        assert flow.pv_power is None


class TestAlert:
    def test_parses_the_payload(self) -> None:
        records = load_fixture("device_warring_list.json")["dataList"]
        if not records:
            pytest.skip("the recorded installation has no active warning")
        alert = Alert.from_payload(records[0])
        assert alert.id
        assert alert.title is not None

    def test_a_treated_alert_is_inactive(self) -> None:
        assert Alert.from_payload({"id": "1", "status": "1"}).is_active is False

    def test_an_unknown_status_is_neither(self) -> None:
        assert Alert.from_payload({"id": "1", "status": "weird"}).is_active is None
        assert Alert.from_payload({"id": "1"}).is_active is None


class TestAlertGroup:
    def test_parses_nested_alerts(self) -> None:
        group = AlertGroup.from_payload(
            {
                "deviceSn": "BAT0001",
                "count": 2,
                "dataList": [{"id": "a"}, {"id": "b"}],
            }
        )
        assert group.device_sn == "BAT0001"
        assert group.count == 2
        assert len(group.alerts) == 2
        assert group.alerts[0].id == "a"

    def test_counts_the_nested_alerts_when_absent(self) -> None:
        group = AlertGroup.from_payload({"dataList": [{"id": "a"}]})
        assert group.count == 1
