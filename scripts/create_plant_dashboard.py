#!/usr/bin/env python3
"""Create a Home Assistant dashboard with one view per Felicity Solar plant.

Home Assistant has a **single** Energy Dashboard for the whole instance, so
there is no built-in way to show "the energy page of Antares" and "the energy
page of Antupirén" separately. The built-in panel can, however, hold one
**solar source per plant**, which already separates them in the graphs.

This script adds the missing piece: a dashboard with a view per plant, where
each view shows that plant's own production history and live values. The
entities are **discovered** from the running instance, so nothing is
hardcoded and a plant with unusual names still works.

Usage::

    export HA_URL="http://192.168.1.5:8123"
    export HA_TOKEN="<long-lived access token>"
    uv run python scripts/create_plant_dashboard.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

import aiohttp

#: The prefix of the entities of each plant, as the integration names them.
PLANTS: tuple[tuple[str, str], ...] = (
    ("Antares", "antares"),
    ("Antupirén", "antupiren"),
)

DASHBOARD_TITLE = "Felicity Solar"
DASHBOARD_ICON = "mdi:solar-power"


def _entities_of(prefix: str, known: set[str], suffix: str) -> list[str]:
    """Return the entities of a plant that really exist."""
    candidate = f"sensor.{prefix}_{suffix}"
    return [candidate] if candidate in known else []


def _plant_view(title: str, prefix: str, known: set[str]) -> dict[str, Any]:
    """Build the view of one plant, with the entities that exist."""
    energy = _entities_of(prefix, known, "plant_pv_energy_today") + _entities_of(
        prefix, known, "plant_pv_energy_month"
    )
    energy += _entities_of(prefix, known, "plant_pv_energy_total")
    energy += _entities_of(prefix, known, "plant_load_energy_today")
    energy += _entities_of(prefix, known, "plant_grid_import_today")
    energy += _entities_of(prefix, known, "plant_grid_export_today")

    battery = _entities_of(prefix, known, "plant_battery_charging_today")
    battery += _entities_of(prefix, known, "plant_battery_discharge_today")
    battery += _entities_of(prefix, known, "plant_battery_charging_total")
    battery += _entities_of(prefix, known, "plant_battery_discharge_total")

    # El SOC de la bateria: cualquier sensor de SOC de esa planta.
    soc = [
        entity
        for entity in sorted(known)
        if entity.startswith(f"sensor.{prefix}_") and entity.endswith("_battery_state_of_charge")
    ]

    cards: list[dict[str, Any]] = [
        {"type": "heading", "heading": title, "icon": "mdi:solar-power"},
    ]

    total = _entities_of(prefix, known, "plant_pv_energy_total")
    if total:
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Producción acumulada",
                "statistic": total[0],
                "chart_type": "bar",
                "period": "month",
                "days_to_show": 365,
            }
        )

    power = _entities_of(prefix, known, "plant_pv_power")
    if power:
        cards.append(
            {
                "type": "history-graph",
                "title": "Potencia FV",
                "entities": [{"entity": power[0], "name": "Producción"}],
                "hours_to_show": 24,
            }
        )

    if energy:
        cards.append(
            {
                "type": "entities",
                "title": "Energía",
                "show_header_toggle": False,
                "entities": energy,
            }
        )
    if battery:
        cards.append(
            {
                "type": "entities",
                "title": "Batería",
                "show_header_toggle": False,
                "entities": battery,
            }
        )
    if soc:
        cards.append(
            {
                "type": "gauge",
                "title": "Batería (SOC)",
                "entity": soc[0],
                "min": 0,
                "max": 100,
                "severity": {"green": 20, "yellow": 40, "red": 0},
            }
        )

    return {
        "title": title,
        "type": "sections",
        "max_columns": 3,
        "cards": cards,
    }


def _summary_view(known: set[str]) -> dict[str, Any]:
    """The view with the totals of every plant."""
    totals = [
        entity
        for entity in (
            "sensor.felicity_solar_total_pv_energy_all_plants",
            "sensor.felicity_solar_total_grid_import_all_plants",
            "sensor.felicity_solar_total_grid_export_all_plants",
            "sensor.felicity_solar_total_battery_charging_all_plants",
            "sensor.felicity_solar_total_battery_discharge_all_plants",
        )
        if entity in known
    ]
    cards: list[dict[str, Any]] = [
        {"type": "heading", "heading": "Todas las plantas", "icon": "mdi:solar-power-variant"}
    ]
    if "sensor.felicity_solar_total_pv_energy_all_plants" in known:
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Producción acumulada",
                "statistic": "sensor.felicity_solar_total_pv_energy_all_plants",
                "chart_type": "bar",
                "period": "month",
                "days_to_show": 365,
            }
        )
    if "sensor.felicity_solar_total_pv_power_all_plants" in known:
        cards.append(
            {
                "type": "history-graph",
                "title": "Potencia FV total",
                "entities": [
                    {
                        "entity": "sensor.felicity_solar_total_pv_power_all_plants",
                        "name": "Producción",
                    }
                ],
                "hours_to_show": 24,
            }
        )
    if totals:
        cards.append(
            {
                "type": "entities",
                "title": "Totales",
                "show_header_toggle": False,
                "entities": totals,
            }
        )
    cards.append(
        {
            "type": "vertical-stack",
            "title": "Panel de Energía de Home Assistant",
            "cards": [
                {"type": "energy-date-selection", "collection_key": "energy_felicity"},
                {"type": "energy-solar-graph", "title": "Producción solar"},
                {"type": "energy-usage-graph", "title": "Consumo"},
            ],
        }
    )
    return {"title": "Resumen", "type": "sections", "max_columns": 3, "cards": cards}


def build_dashboard(known: set[str]) -> dict[str, Any]:
    """Build the dashboard configuration."""
    views = [_summary_view(known)]
    views.extend(_plant_view(title, prefix, known) for title, prefix in PLANTS)
    return {"views": views}


async def _entities(session: aiohttp.ClientSession, url: str) -> set[str]:
    """Return the entity ids of the instance."""
    async with session.get(f"{url}/api/states") as response:
        return {state["entity_id"] for state in await response.json()}


async def main() -> int:
    """Create or update the dashboard."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="only show the config")
    parser.add_argument("--url-path", default="felicity-solar", help="URL of the dashboard")
    args = parser.parse_args()

    url = os.environ.get("HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not url or not token:
        print("HA_URL and HA_TOKEN are required")
        return 2

    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        known = await _entities(session, url)
        config = build_dashboard(known)
        if args.dry_run:
            import json

            print(json.dumps(config, indent=2, ensure_ascii=False))
            return 0

        ws_url = url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        async with session.ws_connect(ws_url) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            await ws.receive_json()

            await ws.send_json({"id": 1, "type": "lovelace/dashboards/list"})
            existing = await ws.receive_json()
            found = any(
                d.get("url_path") == args.url_path for d in existing.get("result", [])
            )

            if found:
                await ws.send_json(
                    {
                        "id": 2,
                        "type": "lovelace/config/save",
                        "url_path": args.url_path,
                        "config": config,
                    }
                )
                response = await ws.receive_json()
                print(f"dashboard '{args.url_path}' actualizado: {response.get('success')}")
            else:
                await ws.send_json(
                    {
                        "id": 2,
                        "type": "lovelace/dashboards/create",
                        "url_path": args.url_path,
                        "title": DASHBOARD_TITLE,
                        "icon": DASHBOARD_ICON,
                        "show_in_sidebar": True,
                        "require_admin": False,
                        "mode": "storage",
                    }
                )
                response = await ws.receive_json()
                if not response.get("success"):
                    print(f"ERROR al crear: {response.get('error')}")
                    return 1
                print(f"dashboard '{args.url_path}' creado")

                await ws.send_json(
                    {
                        "id": 3,
                        "type": "lovelace/config/save",
                        "url_path": args.url_path,
                        "config": config,
                    }
                )
                response = await ws.receive_json()
                print(f"configuracion guardada: {response.get('success')}")

    print(f"\nAbre: {url.rstrip('/')}/{args.url_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
