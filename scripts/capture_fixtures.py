#!/usr/bin/env python3
"""Capture the FSolar API payloads used by the contract tests.

The fixtures are captured from the live API and then redacted, so that no
serial number, plant id, address or credential ever reaches the repository.

Usage::

    FELICITY_TEST_EMAIL=... FELICITY_TEST_PASSWORD=... \\
        uv run python scripts/capture_fixtures.py

The result is written to ``packages/felicity-client/tests/fixtures/``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from felicity_client import FelicityClient

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "packages/felicity-client/tests/fixtures"

#: Keys whose value is an identifier and must be replaced by a stable alias.
_ALIAS_KEYS = (
    "deviceSn",
    "invDeviceSn",
    "plantId",
    "plantName",
    "id",
    "alias",
    "address",
    "collectorSn",
    "collectorSn2",
    "masterDeviceSn",
    "invSn",
    "parentId",
    "owner",
    "createUserId",
    "modifyUserId",
    "userId",
    "userName",
    "email",
    "password",
    "token",
)

#: Free text that may contain an address, a name or a person.
_FREE_TEXT = (
    "plantName",
    "alias",
    "address",
    "deviceName",
    "name",
    "userName",
    "email",
    "ownerName",
    "installer",
    "countryName",
    "phone",
    "contact",
)


def _redact(payload: Any, aliases: dict[str, str]) -> Any:
    """Replace the identifiers of a payload with stable aliases."""
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _ALIAS_KEYS and isinstance(value, str) and value:
                result[key] = _alias(value, aliases)
            elif key in _FREE_TEXT and isinstance(value, str) and value:
                result[key] = f"<{key}>"
            else:
                result[key] = _redact(value, aliases)
        return result
    if isinstance(payload, list):
        return [_redact(item, aliases) for item in payload]
    return payload


def _alias(value: str, aliases: dict[str, str]) -> str:
    """Return a stable, meaningless alias for an identifier.

    The alias is keyed on the **value** alone, so the same plant id gets the
    same alias in the plant list and in the device list. Keying on the field
    name instead would break the relation between the two.
    """
    if value not in aliases:
        aliases[value] = f"ID{len(aliases) + 1:04d}"
    return aliases[value]


def _strip_sensitive(data: Any) -> Any:
    """Remove the keys that must never be captured at all."""
    if isinstance(data, dict):
        return {
            key: _strip_sensitive(value)
            for key, value in data.items()
            if key not in {"token", "password", "userName", "email", "authorization"}
        }
    if isinstance(data, list):
        return [_strip_sensitive(item) for item in data]
    return data


async def capture() -> dict[str, Any]:
    """Capture every payload the client relies on."""
    email = os.environ["FELICITY_TEST_EMAIL"]
    password = os.environ["FELICITY_TEST_PASSWORD"]
    aliases: dict[str, str] = {}
    fixtures: dict[str, Any] = {}

    async with FelicityClient(email, password) as client:
        fixtures["list_plant.json"] = await client.http.post(
            "/plant/list_plant", json={"pageNum": 1, "pageSize": 50}
        )

        plants = await client.list_plants()
        if plants:
            fixtures["plant_details.json"] = await client.http.post(
                "/plant/plantDetails", json={"plantId": plants[0].id}
            )

        devices = await client.list_devices()
        fixtures["list_device_all_type.json"] = await client.http.post(
            "/device/list_device_all_type",
            json={
                "pageNum": 1,
                "pageSize": 50,
                "deviceSn": "",
                "status": "",
                "sampleFlag": "",
                "oscFlag": "",
            },
        )

        inverter = next((d for d in devices if d.product_type.name == "INVERTER"), None)
        battery = next((d for d in devices if d.product_type.name == "BATTERY"), None)

        if inverter is not None:
            fixtures["snapshot_inverter.json"] = await client.http.post(
                "/device/get_device_snapshot",
                json={
                    "deviceSn": inverter.serial_number,
                    "deviceType": "BP",
                    "dateStr": "2026-10-21 12:00:00",
                },
            )
            if inverter.plant_id:
                fixtures["get_energy_flow2.json"] = await client.http.get(
                    "/device/get_energy_flow2",
                    params={
                        "deviceSn": inverter.serial_number,
                        "plantId": inverter.plant_id,
                    },
                )

        if battery is not None:
            fixtures["snapshot_battery.json"] = await client.http.post(
                "/device/get_device_snapshot",
                json={
                    "deviceSn": battery.serial_number,
                    "deviceType": "BP",
                    "dateStr": "2026-10-21 12:00:00",
                },
            )

        fixtures["device_warring_list.json"] = await client.http.post(
            "/device/device_warring_list",
            json={
                "pageNum": 1,
                "pageSize": 50,
                "leftDate": "2026-09-21 00:00:00",
                "rightDate": "2026-10-21 23:59:59",
            },
        )

        # A successful login, with the token replaced by a dummy.
        fixtures["userlogin.json"] = {
            "code": 200,
            "data": {"token": "Bearer_fixture.token.value"},
            "message": "success",
        }

    return {
        name: _redact(_strip_sensitive(payload), aliases)
        for name, payload in fixtures.items()
        if name != "userlogin.json"
    } | {"userlogin.json": fixtures["userlogin.json"]}


def main() -> int:
    """Capture and write the fixtures."""
    if not os.environ.get("FELICITY_TEST_EMAIL"):
        print("FELICITY_TEST_EMAIL and FELICITY_TEST_PASSWORD are required")
        return 2

    fixtures = asyncio.run(capture())
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in fixtures.items():
        target = FIXTURE_DIR / name
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {target.name}")

    # The leak check: no serial number or account id may survive.
    blob = json.dumps(fixtures)
    leaked = set(
        re.findall(r'"(?:deviceSn|invDeviceSn|owner|parentId|userId)"\s*:\s*"([^"]+)"', blob)
    )
    suspicious = {value for value in leaked if not re.fullmatch(r"[A-Z]+[A-Z0-9]*\d+", value)}
    if suspicious:
        print(f"WARNING: identifiers still present: {sorted(suspicious)[:5]}", file=sys.stderr)
        return 1
    print(f"redaction ok: {len(fixtures)} fixture(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
