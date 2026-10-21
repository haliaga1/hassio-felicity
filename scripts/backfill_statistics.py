#!/usr/bin/env python3
"""Backfill the recorder statistics of the Felicity Solar energy counters.

The lifetime counters of the integration start counting from the moment the
integration is installed. Until the recorder has a full period of history,
the Home Assistant Energy Dashboard shows **0 kWh** even though the plant
produced energy today.

The FSolar API publishes the production accumulated over the day
(``todayPv``) and the lifetime total (``accPv``). The difference is exactly
the energy produced since midnight, so it can be imported into the recorder
as the statistic of the first hour of the day. The imported value is
therefore **true**, not an estimate.

Usage::

    export HA_URL="http://192.168.1.5:8123"
    export HA_TOKEN="<long-lived access token>"
    uv run python scripts/backfill_statistics.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from typing import Any

import aiohttp

#: The entity to backfill -> the daily sensor that holds the same figure.
TARGETS: dict[str, str] = {
    "sensor.antares_plant_pv_energy_total": "sensor.antares_plant_pv_energy_today",
    "sensor.antupiren_plant_pv_energy_total": "sensor.antupiren_plant_pv_energy_today",
    "sensor.antares_plant_grid_import_total": "sensor.antares_plant_grid_import_today",
    "sensor.antares_plant_grid_export_total": "sensor.antares_plant_grid_export_today",
    # El agregado de todas las plantas: la suma de las diarias.
    "sensor.felicity_solar_total_pv_energy_all_plants": None,  # type: ignore[dict-item]
    "sensor.felicity_solar_total_grid_import_all_plants": None,  # type: ignore[dict-item]
    "sensor.felicity_solar_total_grid_export_all_plants": None,  # type: ignore[dict-item]
}

#: El agregado se obtiene sumando las plantas, no de un sensor diario.
AGGREGATE_SOURCES: dict[str, list[str]] = {
    "sensor.felicity_solar_total_pv_energy_all_plants": [
        "sensor.antares_plant_pv_energy_today",
        "sensor.antupiren_plant_pv_energy_today",
    ],
    "sensor.felicity_solar_total_grid_import_all_plants": [
        "sensor.antares_plant_grid_import_today",
        "sensor.antupiren_plant_grid_import_today",
    ],
    "sensor.felicity_solar_total_grid_export_all_plants": [
        "sensor.antares_plant_grid_export_today",
        "sensor.antupiren_plant_grid_export_today",
    ],
}

UNIT_OF_MEASUREMENT = "kWh"
UNIT_CLASS = "energy"
#: The recorder requires the source to be its own domain.
SOURCE = "recorder"


async def _import_statistic(
    session: aiohttp.ClientSession,
    url: str,
    token: str,
    metadata: dict[str, Any],
    stats: list[dict[str, Any]],
) -> str:
    """Import one statistic through the Home Assistant websocket."""
    ws_url = url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
    async with session.ws_connect(ws_url) as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        auth = await ws.receive_json()
        if auth.get("type") != "auth_ok":
            return f"ERROR {auth.get('message')}"
        await ws.send_json(
            {
                "id": 1,
                "type": "recorder/import_statistics",
                "metadata": metadata,
                "stats": stats,
            }
        )
        response = await ws.receive_json()
    if not response.get("success"):
        return f"ERROR {response.get('error')}"
    return "importada"


async def main() -> int:
    """Run the backfill."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="only show what would be done")
    args = parser.parse_args()

    url = os.environ.get("HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not url or not token:
        print("HA_URL and HA_TOKEN are required")
        return 2

    #: The recorder rejects naive timestamps.
    today = datetime.now(UTC).astimezone().replace(hour=0, minute=0, second=0, microsecond=0)

    async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {token}"}) as session:
        states: dict[str, Any] = {}
        async with session.get(f"{url}/api/states") as response:
            for state in await response.json():
                states[state["entity_id"]] = state

        for entity_id, daily_entity in TARGETS.items():
            if entity_id not in states:
                print(f"  ! {entity_id} no existe, se omite")
                continue

            if daily_entity is None:
                # El agregado: la suma de las plantas.
                sources = AGGREGATE_SOURCES.get(entity_id, [])
                total = 0.0
                for source in sources:
                    source_state = states.get(source)
                    if source_state is None:
                        continue
                    try:
                        total += float(source_state["state"])
                    except (TypeError, ValueError):
                        continue
                value = total
            else:
                daily_state = states.get(daily_entity)
                if daily_state is None:
                    print(f"  ! {daily_entity} no existe, se omite")
                    continue
                try:
                    value = float(daily_state["state"])
                except (TypeError, ValueError):
                    print(f"  ! {daily_entity} no es un numero, se omite")
                    continue
            if value <= 0:
                print(f"  - {entity_id}: nada que rellenar ({value} kWh)")
                continue

            metadata = {
                "has_mean": False,
                "has_sum": True,
                "name": entity_id.split(".", 1)[1].replace("_", " ").title(),
                "source": SOURCE,
                "statistic_id": entity_id,
                "unit_class": UNIT_CLASS,
                "unit_of_measurement": UNIT_OF_MEASUREMENT,
            }
            stats = [{"start": today.isoformat(), "sum": value}]

            if args.dry_run:
                print(f"  * {entity_id}: importaria {value} kWh de {today.isoformat()}")
                continue

            result = await _import_statistic(session, url, token, metadata, stats)
            print(f"  * {entity_id}: {result} ({value} kWh)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
