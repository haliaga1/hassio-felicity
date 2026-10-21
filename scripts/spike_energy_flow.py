#!/usr/bin/env python3
"""Spike: what does the energy flow endpoint actually return?

Closes the open question Q2 documented in
``docs/spikes/energy-flow-shape.md``.

Usage::

    FELICITY_TEST_EMAIL=... FELICITY_TEST_PASSWORD=... \\
        FELICITY_TEST_DEVICE_SN=... \\
        uv run python scripts/spike_energy_flow.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from felicity_client import FelicityClient

NUMERIC = (int, float)


async def main() -> int:
    """Print the raw payloads of the energy flow and the snapshot."""
    email = os.environ.get("FELICITY_TEST_EMAIL")
    password = os.environ.get("FELICITY_TEST_PASSWORD")
    if not email or not password:
        print("FELICITY_TEST_EMAIL and FELICITY_TEST_PASSWORD are required")
        return 2

    async with FelicityClient(email, password) as client:
        devices = await client.list_devices()
        if not devices:
            print("The account has no device")
            return 1

        serial_number = os.environ.get("FELICITY_TEST_DEVICE_SN")
        device = next((d for d in devices if d.serial_number == serial_number), devices[0])
        plant_id = device.plant_id or ""
        print(f"Device: {device.serial_number} ({device.model})")
        print(f"Plant:  {plant_id} ({device.plant_name})")

        print("\n=== get_device_snapshot (numeric fields) ===")
        snapshot = await client.get_snapshot(device.serial_number)
        for key, value in sorted(snapshot.raw.items()):
            if isinstance(value, NUMERIC) and not isinstance(value, bool):
                print(f"  {key:32} = {value}")

        print("\n=== get_energy_flow2 (raw) ===")
        flow = await client.get_energy_flow(device.serial_number, plant_id)
        print(json.dumps(flow.raw, indent=2, ensure_ascii=False))

        print("\n=== get_energy_flow2 (numeric fields) ===")
        for key, value in sorted(flow.values.items()):
            print(f"  {key:32} = {value}")

        print(
            "\nNow compare the signs with the equipment doing something "
            "different:\n"
            "  - charging the battery  -> bmsPower > 0 or < 0?\n"
            "  - discharging the battery -> bmsPower > 0 or < 0?\n"
            "  - importing from the grid -> gridPower > 0 or < 0?\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
