#!/usr/bin/env python3
"""Create a Home Assistant dashboard for each Felicity Solar plant.

Home Assistant has a **single** Energy Dashboard for the whole instance, so
there is no built-in way to show "the energy page of Antares" and "the energy
page of Antupirén" separately. The built-in panel can hold one *solar source
per plant*, which already separates them in the graphs.

This script adds the missing piece: **one dashboard per plant**, so each one
gets its own tab in the sidebar, plus a summary dashboard. The entities are
**discovered** from the running instance, so nothing is hardcoded and a plant
whose battery has no alias is still handled.

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

#: The plant title, the prefix of its entities and the slug of its dashboard.
PLANTS: tuple[tuple[str, str, str], ...] = (
    ("Antares", "antares", "antares"),
    ("Antupirén", "antupiren", "antupiren"),
)

DASHBOARD_ICON = "mdi:solar-power"


def _entities_of(prefix: str, known: set[str], suffix: str) -> list[str]:
    """Return the entities of a plant that really exist."""
    candidate = f"sensor.{prefix}_{suffix}"
    return [candidate] if candidate in known else []


def _plant_cards(prefix: str, known: set[str]) -> list[dict[str, Any]]:
    """Build the cards of a plant's page, mirroring the official app."""
    cards: list[dict[str, Any]] = []

    # "Datos de Hoy": PV, carga, descarga, entrada y salida de red.
    hoy = _entities_of(prefix, known, "plant_pv_energy_today")
    hoy += _entities_of(prefix, known, "plant_load_energy_today")
    hoy += _entities_of(prefix, known, "plant_battery_charging_today")
    hoy += _entities_of(prefix, known, "plant_battery_discharge_today")
    hoy += _entities_of(prefix, known, "plant_grid_import_today")
    hoy += _entities_of(prefix, known, "plant_grid_export_today")
    if hoy:
        cards.append(
            {
                "type": "entities",
                "title": "Datos de hoy",
                "show_header_toggle": False,
                "entities": hoy,
            }
        )

    # "Datos Estadisticos": mes, ano y total.
    stats = _entities_of(prefix, known, "plant_pv_energy_this_month")
    stats += _entities_of(prefix, known, "plant_pv_energy_total")
    if stats:
        cards.append(
            {
                "type": "entities",
                "title": "Datos estadísticos",
                "show_header_toggle": False,
                "entities": stats,
            }
        )

    # El estado de carga de la bateria.
    soc = [
        entity
        for entity in sorted(known)
        if entity.startswith(f"sensor.{prefix}_") and entity.endswith("_battery_state_of_charge")
    ]
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

    # La potencia de hoy, en su grafico.
    power = _entities_of(prefix, known, "plant_pv_power")
    if power:
        cards.append(
            {
                "type": "history-graph",
                "title": "Potencia FV (24 h)",
                "entities": [{"entity": power[0], "name": "Producción"}],
                "hours_to_show": 24,
            }
        )

    # El grafico de generacion de la pagina de Energia, pero de esta planta.
    total = _entities_of(prefix, known, "plant_pv_energy_total")
    if total:
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Generación (acumulado)",
                "statistic": total[0],
                "chart_type": "bar",
                "period": "day",
                "days_to_show": 7,
            }
        )
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Generación (mensual)",
                "statistic": total[0],
                "chart_type": "bar",
                "period": "month",
                "days_to_show": 365,
            }
        )

    return cards


def _summary_cards(known: set[str]) -> list[dict[str, Any]]:
    """Build the cards of the summary page."""
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
    cards: list[dict[str, Any]] = []
    if totals:
        cards.append(
            {
                "type": "entities",
                "title": "Totales (todas las plantas)",
                "show_header_toggle": False,
                "entities": totals,
            }
        )
    power = _entities_of("felicity_solar", known, "total_pv_power_all_plants")
    if power:
        cards.append(
            {
                "type": "history-graph",
                "title": "Potencia FV total (24 h)",
                "entities": [{"entity": power[0], "name": "Producción"}],
                "hours_to_show": 24,
            }
        )
    # El grafico de generacion de la pagina de Energia, con una serie por planta.
    cards.append(
        {
            "type": "energy-solar-graph",
            "title": "Generación (todas las plantas)",
        }
    )
    return cards


def build_dashboards(known: set[str]) -> dict[str, dict[str, Any]]:
    """Build the configuration of the dashboard.

    A single dashboard with one **view per plant**: Home Assistant shows the
    views as tabs of the same page.
    """
    views: list[dict[str, Any]] = [
        {
            "title": "Resumen",
            "path": "resumen",
            "type": "masonry",
            "cards": _summary_cards(known),
        }
    ]
    for title, prefix, slug in PLANTS:
        views.append(
            {
                "title": title,
                "path": slug,
                "type": "masonry",
                "cards": _plant_cards(prefix, known),
            }
        )
    return {
        "felicity-solar": {
            "title": "Felicity Solar",
            "views": views,
        }
    }


async def _entities(session: aiohttp.ClientSession, url: str) -> set[str]:
    """Return the entity ids of the instance."""
    async with session.get(f"{url}/api/states") as response:
        return {state["entity_id"] for state in await response.json()}


async def _save_dashboard(
    ws: aiohttp.ClientWSMessage,
    url_path: str,
    title: str,
    config: dict[str, Any],
    next_id: int,
) -> tuple[str, int]:
    """Create the dashboard if needed and save its configuration."""
    await ws.send_json({"id": next_id, "type": "lovelace/dashboards/list"})
    existing = await ws.receive_json()
    next_id += 1
    found = any(d.get("url_path") == url_path for d in existing.get("result", []))

    if not found:
        await ws.send_json(
            {
                "id": next_id,
                "type": "lovelace/dashboards/create",
                "url_path": url_path,
                "title": title,
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "require_admin": False,
                "mode": "storage",
            }
        )
        created = await ws.receive_json()
        next_id += 1
        if not created.get("success"):
            return f"ERROR al crear: {created.get('error')}", next_id

    await ws.send_json(
        {
            "id": next_id,
            "type": "lovelace/config/save",
            "url_path": url_path,
            "config": config,
        }
    )
    saved = await ws.receive_json()
    next_id += 1
    if not saved.get("success"):
        return f"ERROR al guardar: {saved.get('error')}", next_id
    return "ok", next_id


async def main() -> int:
    """Create or update the dashboards."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="only show the config")
    args = parser.parse_args()

    url = os.environ.get("HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not url or not token:
        print("HA_URL and HA_TOKEN are required")
        return 2

    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        known = await _entities(session, url)
        dashboards = build_dashboards(known)
        if args.dry_run:
            import json

            print(json.dumps(dashboards, indent=2, ensure_ascii=False))
            return 0

        ws_url = url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        async with session.ws_connect(ws_url) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            await ws.receive_json()

            next_id = 10
            for url_path, spec in dashboards.items():
                result, next_id = await _save_dashboard(ws, url_path, spec["title"], spec, next_id)
                print(f"  {url_path:26} {result}")

    print(f"\nAbre: {url.rstrip('/')}/felicity-solar")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
