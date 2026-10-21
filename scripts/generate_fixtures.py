#!/usr/bin/env python3
"""Generate the contract fixtures used by the offline test suite.

The fixtures mirror the payloads captured from the live FSolar API. They are
committed so that the test suite never needs credentials, and so that a change
in the upstream contract shows up as a failing test.

Run with ``uv run python scripts/generate_fixtures.py``.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "packages/felicity-client/tests/fixtures"

#: A JWT with a valid structure and a far-future expiry.
_FAR_FUTURE = 4102444800  # 2100-01-01


def _b64url(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_token(exp: int = _FAR_FUTURE) -> str:
    """Build a JWT-shaped bearer token."""
    header = _b64url({"alg": "HS512", "typ": "JWT"})
    claims = _b64url({"exp": exp, "userName": "fixture@example.com", "iat": 1700000000})
    signature = base64.urlsafe_b64encode(b"fixture-signature-not-a-real-key").decode().rstrip("=")
    return f"Bearer_{header}.{claims}.{signature}"


USERLOGIN = {
    "code": 200,
    "data": {"token": make_token(), "userId": "fixture-user-id"},
    "message": "success",
}

LIST_PLANT = {
    "code": 200,
    "data": {
        "dataList": [
            {
                "id": "plant-0001",
                "plantName": "Casa Principal",
                "address": "Av. Siempre Viva 742, Santiago",
                "countryId": "CL",
                "latitude": "-33.4489",
                "longitude": "-70.6693",
                "ratedPower": "10000",
                "deviceCount": 3,
            },
            {
                "id": "plant-0002",
                "plantName": "Casa Secondary",
                "address": "Camping 12, Valpo",
                "countryId": "CL",
                "latitude": "-33.0472",
                "longitude": "-71.6127",
                "ratedPower": "5000",
                "deviceCount": 1,
            },
        ],
        "total": 2,
        "pageNum": 1,
        "pageSize": 50,
    },
    "message": "success",
}

PLANT_DETAILS = {
    "code": 200,
    "data": {
        "id": "plant-0001",
        "plantName": "Casa Principal",
        "address": "Av. Siempre Viva 742, Santiago",
        "countryId": "CL",
        "installCapacity": "10.0",
        "createTime": "2024-03-11 14:22:03",
    },
    "message": "success",
}

LIST_DEVICE_ALL_TYPE = {
    "code": 200,
    "data": {
        "dataList": [
            {
                "deviceSn": "INV0001",
                "deviceModel": "IVGM8KLPT2G1",
                "deviceType": "IVGM",
                "productTypeEnum": "HIGH_FREQUENCY_INVERTER",
                "typeCode": 119,
                "subType": 516,
                "plantId": "plant-0001",
                "plantName": "Casa Principal",
                "status": "online",
                "firmwareVersion": "1.2.3",
                "alias": "Inversor Principal",
                "collectorSn": "COL0001",
                "ratedPower": "8000",
            },
            {
                "deviceSn": "BAT0001",
                "deviceModel": "FLA48100TG2",
                "deviceType": "FLA",
                "productTypeEnum": "LITHIUM_BATTERY_PACK",
                "typeCode": 119,
                "subType": 258,
                "plantId": "plant-0001",
                "plantName": "Casa Principal",
                "status": "online",
                "firmwareVersion": "2.0.1",
                "alias": "Bateria 1",
                "collectorSn": "COL0001",
                "ratedEnergy": "5.12",
            },
            {
                "deviceSn": "CTL0001",
                "deviceModel": "HP5000",
                "deviceType": "CONTROLLER",
                "productTypeEnum": "CONTROLLER",
                "plantId": "plant-0001",
                "plantName": "Casa Principal",
                "status": "offline",
                "firmwareVersion": "0.9.9",
                "alias": "Controlador",
                "ratedPower": "5000",
            },
            {
                "deviceSn": "INV0002",
                "deviceModel": "IVGM5KLPT2G1",
                "deviceType": "IVGM",
                "productTypeEnum": "HIGH_FREQUENCY_INVERTER",
                "typeCode": 119,
                "subType": 516,
                "plantId": "plant-0002",
                "plantName": "Casa Secondary",
                "status": "offline",
                "firmwareVersion": "1.2.3",
                "alias": "Inversor Secundario",
                "collectorSn": "COL0002",
                "ratedPower": "5000",
            },
        ],
        "total": 4,
        "pageNum": 1,
        "pageSize": 50,
    },
    "message": "success",
}

SNAPSHOT_INVERTER = {
    "code": 200,
    "data": {
        "deviceSn": "INV0001",
        "deviceModel": "IVGM8KLPT2G1",
        "deviceType": "IVGM",
        "productTypeEnum": "HIGH_FREQUENCY_INVERTER",
        "typeCode": 119,
        "subType": 516,
        "plantName": "Casa Principal",
        "plantId": "plant-0001",
        "status": "online",
        "workModeStr": "Normal",
        "firmwareVersion": "1.2.3",
        "collectorSn": "COL0001",
        "ratedPower": "8000",
        "nameplateRatedPower": "8000",
        "dataTime": 1767225600000,
        "dataTimeStr": "2026-01-01 12:00:00",
        "timeZone": "GMT+08:00",
        "warningCount": 0,
        "reportFreq": 300,
        "wifiSignal": -55,
        "voltageLevel": 1,
        "inputPhaseNum": 1,
        "outputPhaseNum": 1,
        "pvChannelNum": 2,
        "batCount": 1,
        "hasMaster": 1,
        "activationFlag": True,
        "sampleFlag": 0,
        "isOwnerDevice": 1,
        "pvVolt": "312.5",
        "pvInCurr": "9.42",
        "pvPower": "2943.8",
        "pvTotalPower": "2943.8",
        "pv1Power": "1500.2",
        "pv2Power": "1443.6",
        "pvTotalVoltage": "312.5",
        "ePvToday": "12.480",
        "ePvTotal": "1842.660",
        "acRInVolt": "231.4",
        "acRInFreq": "50.01",
        "acRInPower": "1204.5",
        "acROutVolt": "230.8",
        "acROutCurr": "5.21",
        "acROutFreq": "50.00",
        "acTotalOutActPower": "1204.5",
        "loadPercent": "48",
        "eLoadToday": "14.220",
        "eLoadTotal": "2011.480",
        "emsVoltage": "53.12",
        "emsCurrent": "-12.40",
        "emsPower": "-658.5",
        "emsSoc": "87",
        "emsSoh": "99",
        "emsCapacity": "5.120",
        "totalEmsCapacity": "5.120",
        "battVolt": "53.05",
        "battCurr": "-12.55",
        "battSoc": "87",
        "battSoh": "99",
        "battCapacity": "5.120",
        "bmsPower": "-658.5",
        "bmsChargingState": 0,
        "bmsState": "Normal",
        "bmsVoltageList": ["3.325", "3.330", "3.328", "3.331", "3.327", "3.329"],
        "cellTempList": ["28.5", "28.7", "28.6", "28.8", "28.4", "28.6"],
        "cellTemp1": "28.5",
        "cellTemp2": "28.7",
        "cellTemp3": "28.6",
        "cellTemp4": "28.8",
        "maxVoltage2bms": "3.331",
        "minVoltage2bms": "3.325",
        "maxVoltageNum2bms": "5",
        "minVoltageNum2bms": "2",
        "remainingBatteryEnergy1": "4.454",
        "BMSLCVolt": "58.0",
        "BMSLDVolt": "48.0",
        "BMSLCCurr": "50.0",
        "BMSLDCurr": "50.0",
        "seriesParallelStatus": 2,
        "tempMax": "31.2",
        "tempMin": "24.8",
        "devTempMax": "45.6",
        "devTempMin": "28.1",
        "totalEnergy": "3842.150",
        "totalEnergyUnit": "kWh",
        "energy": "0.000",
        "energyUnit": "kWh",
        "bmsFlag": False,
        "bmsFlagStr": "Normal",
        "batBmsOnlineStr": "Online",
        "ctIsOnelineStr": "Online",
        "ronoffStr": "On",
        "outModStr": "Normal",
        "oSPriStr": "Normal",
        "cSPriStr": "Normal",
        "standStr": "Standby",
        "standFlag": 0,
        "grsmtr": 0,
        "electricityMeterLink": 0,
        "electricityMeterLinkStr": "None",
        "gunStateStr": "None",
        "parentId": "",
    },
    "message": "success",
}

SNAPSHOT_BATTERY = {
    "code": 200,
    "data": {
        "deviceSn": "BAT0001",
        "deviceModel": "FLA48100TG2",
        "deviceType": "FLA",
        "productTypeEnum": "LITHIUM_BATTERY_PACK",
        "plantName": "Casa Principal",
        "plantId": "plant-0001",
        "status": "online",
        "firmwareVersion": "2.0.1",
        "collectorSn": "COL0001",
        "ratedEnergy": "5.12",
        "batteryCapacity": "5.120",
        "capacity": "5.120",
        "dataTime": 1767225600000,
        "dataTimeStr": "2026-01-01 12:00:00",
        "battVolt": "53.05",
        "battCurr": "-12.55",
        "battSoc": "87",
        "battSoh": "99",
        "battCapacity": "5.120",
        "bmsPower": "-658.5",
        "bmsChargingState": 1,
        "bmsState": "Normal",
        "totalEnergy": "1842.660",
        "totalEnergyUnit": "kWh",
        "tempMax": "31.2",
        "tempMin": "24.8",
        "emsVoltage": "53.12",
        "emsCurrent": "-12.40",
        "emsPower": "-658.5",
        "emsSoc": "87",
        "emsSoh": "99",
        "emsCapacity": "5.120",
        "totalEmsCapacity": "5.120",
        "maxVoltage2bms": "3.331",
        "minVoltage2bms": "3.325",
        "bmsVoltageList": ["3.325", "3.330", "3.328", "3.331"],
        "cellTempList": ["28.5", "28.7", "28.6", "28.8"],
        "remainingBatteryEnergy1": "4.454",
        "wifiSignal": -48,
        "warningCount": 0,
    },
    "message": "success",
}

SNAPSHOT_CONTROLLER = {
    "code": 200,
    "data": {
        "deviceSn": "CTL0001",
        "deviceModel": "HP5000",
        "deviceType": "CONTROLLER",
        "productTypeEnum": "CONTROLLER",
        "plantName": "Casa Principal",
        "plantId": "plant-0001",
        "status": "offline",
        "firmwareVersion": "0.9.9",
        "workModeStr": "Standby",
        "pvVolt": "0",
        "pvInCurr": "0",
        "pvPower": "0",
        "pvTotalPower": "0",
        "emsVoltage": "52.80",
        "emsCurrent": "0",
        "emsPower": "0",
        "bmsChargingState": 0,
        "tempMax": "22.4",
        "devTempMax": "30.2",
        "totalEnergy": "2011.480",
        "totalEnergyUnit": "kWh",
    },
    "message": "success",
}

GET_ENERGY_FLOW2 = {
    "code": 200,
    "data": {
        "deviceSn": "INV0001",
        "plantId": "plant-0001",
        "pvPower": "2943.8",
        "loadPower": "1204.5",
        "batteryPower": "-658.5",
        "gridPower": "1204.5",
        "acRInPower": "1204.5",
        "acTotalOutActPower": "1204.5",
        "emsPower": "-658.5",
        "loadPercent": "48",
        "time": "2026-01-01 12:00:00",
        "status": "online",
        "type": "BP",
    },
    "message": "success",
}

DEVICE_WARRING_LIST = {
    "code": 200,
    "data": {
        "dataList": [
            {
                "id": "warn-9001",
                "deviceSn": "BAT0001",
                "warnTitle": "LowCellVoltage",
                "warnContent": "The lowest cell voltage is below the threshold",
                "warnLevel": "2",
                "status": "0",
                "warnCode": "BMS-018",
                "createTime": "2026-01-01 09:12:44",
            }
        ],
        "total": 1,
    },
    "message": "success",
}

ERROR_RSA = {
    "code": 10010027,
    "message": "RSA ciphertext error",
    "data": "RSA ciphertext error",
}

ERROR_BAD_CREDENTIALS = {
    "code": 10010001,
    "message": "Account or password error",
    "data": "Account or password error",
}

FIXTURES: dict[str, Any] = {
    "userlogin.json": USERLOGIN,
    "userlogin_error_rsa.json": ERROR_RSA,
    "userlogin_error_credentials.json": ERROR_BAD_CREDENTIALS,
    "list_plant.json": LIST_PLANT,
    "plant_details.json": PLANT_DETAILS,
    "list_device_all_type.json": LIST_DEVICE_ALL_TYPE,
    "snapshot_inverter.json": SNAPSHOT_INVERTER,
    "snapshot_battery.json": SNAPSHOT_BATTERY,
    "snapshot_controller.json": SNAPSHOT_CONTROLLER,
    "get_energy_flow2.json": GET_ENERGY_FLOW2,
    "device_warring_list.json": DEVICE_WARRING_LIST,
}


def main() -> None:
    """Write every fixture to disk."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in FIXTURES.items():
        target = FIXTURE_DIR / name
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {target.relative_to(FIXTURE_DIR.parents[4])}")


if __name__ == "__main__":
    main()
