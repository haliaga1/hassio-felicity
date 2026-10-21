"""Unit tests for the model layer: parsing, coercion and null handling."""

from __future__ import annotations

import pytest
from helpers import load_fixture

from felicity_client.models.alerts import Alert, AlertGroup
from felicity_client.models.common import Device, Plant, ProductType
from felicity_client.models.energy import EnergyFlow
from felicity_client.models.snapshot import Snapshot


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


class TestPlant:
    def test_parses_the_payload(self) -> None:
        record = load_fixture("list_plant.json")["data"]["dataList"][0]
        plant = Plant.from_payload(record)
        assert plant.id == "plant-0001"
        assert plant.name == "Casa Principal"
        assert plant.country_id == "CL"
        assert plant.capacity_kw == pytest.approx(10000.0)
        assert plant.raw == record

    def test_tolerates_a_missing_id(self) -> None:
        plant = Plant.from_payload({"plantName": "Sin id"})
        assert plant.id == ""
        assert plant.name == "Sin id"


class TestDevice:
    def test_parses_the_payload(self) -> None:
        record = load_fixture("list_device_all_type.json")["data"]["dataList"][0]
        device = Device.from_payload(record)
        assert device.serial_number == "INV0001"
        assert device.product_type is ProductType.INVERTER
        assert device.model == "IVGM8KLPT2G1"
        assert device.plant_id == "plant-0001"
        assert device.alias == "Inversor Principal"
        assert device.type_code == 119
        assert device.is_online is True

    def test_reports_offline(self) -> None:
        record = load_fixture("list_device_all_type.json")["data"]["dataList"][2]
        assert Device.from_payload(record).is_online is False

    def test_reports_unknown_status_as_none(self) -> None:
        """An unrecognised status must not be reported as offline."""
        assert Device.from_payload({"deviceSn": "X", "status": "weird"}).is_online is None
        assert Device.from_payload({"deviceSn": "X"}).is_online is None


class TestSnapshot:
    def test_parses_the_inverter(self) -> None:
        snapshot = Snapshot.from_payload(load_fixture("snapshot_inverter.json")["data"])
        assert snapshot.device_sn == "INV0001"
        assert snapshot.pv.power == pytest.approx(2943.8)
        assert snapshot.pv.energy_total_kwh == pytest.approx(1842.66)
        assert snapshot.ac_in.power == pytest.approx(1204.5)
        assert snapshot.ac_out.current == pytest.approx(5.21)
        assert snapshot.battery.soc == pytest.approx(87.0)
        assert snapshot.battery.soh == pytest.approx(99.0)
        assert snapshot.battery.capacity_kwh == pytest.approx(5.12)
        assert snapshot.thermal.device_max_c == pytest.approx(45.6)
        assert snapshot.thermal.cell_temperatures[0] == pytest.approx(28.5)
        assert snapshot.totals.total_kwh == pytest.approx(3842.15)
        assert snapshot.work_mode == "Normal"
        assert snapshot.wifi_signal == -55

    def test_parses_the_battery(self) -> None:
        snapshot = Snapshot.from_payload(load_fixture("snapshot_battery.json")["data"])
        assert snapshot.product_type is ProductType.BATTERY
        assert snapshot.battery.remaining_energy_kwh == pytest.approx(4.454)
        assert snapshot.battery.charging_state == 1
        assert snapshot.battery.charging_state_name == "charging"
        assert snapshot.battery.cell_voltages == (3.325, 3.33, 3.328, 3.331)

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

    def test_parses_the_timestamp(self) -> None:
        snapshot = Snapshot.from_payload(load_fixture("snapshot_inverter.json")["data"])
        assert snapshot.timestamp is not None
        assert snapshot.timestamp.year == 2026

    def test_an_unknown_product_type_is_not_fatal(self) -> None:
        snapshot = Snapshot.from_payload({"deviceSn": "X", "productTypeEnum": "NEW_THING"})
        assert snapshot.product_type is ProductType.UNKNOWN
        assert snapshot.device_sn == "X"


class TestEnergyFlow:
    def test_parses_the_payload(self) -> None:
        flow = EnergyFlow.from_payload(load_fixture("get_energy_flow2.json")["data"])
        assert flow.device_sn == "INV0001"
        assert flow.plant_id == "plant-0001"
        assert flow.pv_power == pytest.approx(2943.8)
        assert flow.load_power == pytest.approx(1204.5)
        assert flow.battery_power == pytest.approx(-658.5)
        assert flow.grid_power == pytest.approx(1204.5)

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
        record = load_fixture("device_warring_list.json")["data"]["dataList"][0]
        alert = Alert.from_payload(record)
        assert alert.id == "warn-9001"
        assert alert.device_sn == "BAT0001"
        assert alert.title == "LowCellVoltage"
        assert alert.severity == "2"
        assert alert.code == "BMS-018"
        assert alert.is_active is True
        assert alert.created_at is not None

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
