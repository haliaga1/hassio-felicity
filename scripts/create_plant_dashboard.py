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


def _flow_entities(plant_id: str, registry: dict[str, str]) -> list[str]:
    """Return the flow state sensors of a plant."""
    return _by_unique_id(
        registry,
        (
            f"{plant_id}_plant_grid_flow",
            f"{plant_id}_plant_pv_flow",
            f"{plant_id}_plant_battery_flow",
        ),
    )


def _plant_ids(registry: dict[str, str], states: dict[str, Any]) -> dict[str, str]:
    """Map the plant name to the id used in the unique ids.

    The unique id of a plant sensor starts with the plant id (a number),
    not with the name, so the mapping is read from the ``plant_name``
    attribute of the entities themselves.
    """
    mapping: dict[str, str] = {}
    for unique_id, entity_id in registry.items():
        state = states.get(entity_id, {})
        name = state.get("attributes", {}).get("plant_name")
        if not name:
            continue
        mapping[str(name)] = unique_id.split("_", 1)[0]
    return mapping


def _by_unique_id(registry: dict[str, str], suffixes: tuple[str, ...]) -> list[str]:
    """Resolve entities by their unique identifier.

    The entity id of a sensor is built from the *translated* name of the
    card, so it changes with the wording; the unique id does not. Every
    lookup goes through here.
    """
    found: list[str] = []
    for suffix in suffixes:
        for unique_id, entity_id in registry.items():
            if unique_id.endswith(suffix):
                found.append(entity_id)
                break
    return found


def _plant_cards(
    plant_id: str, prefix: str, known: set[str], registry: dict[str, str]
) -> list[dict[str, Any]]:
    """Build the cards of a plant's page, mirroring the official app."""
    cards: list[dict[str, Any]] = []

    # El flujo en tiempo real, como en la app oficial: PV, carga, bateria
    # cargando/descargando y entrada/salida de red.
    realtime = _by_unique_id(
        registry,
        (
            f"{plant_id}_plant_pv_power",
            f"{plant_id}_plant_load_power",
            f"{plant_id}_plant_battery_charging_power",
            f"{plant_id}_plant_battery_discharging_power",
            f"{plant_id}_plant_grid_import_power",
            f"{plant_id}_plant_grid_export_power",
        ),
    )
    if realtime:
        cards.append(
            {
                "type": "entities",
                "title": "Flujo en tiempo real",
                "show_header_toggle": False,
                "entities": realtime,
            }
        )

    # El estado de cada flujo: de donde viene la energia y donde va.
    # Se buscan por identificador unico, porque el entity_id depende del
    # nombre traducido de la tarjeta.
    flows = _flow_entities(plant_id, registry)
    if flows:
        cards.append(
            {
                "type": "entities",
                "title": "Estado de los flujos",
                "show_header_toggle": False,
                "entities": flows,
            }
        )

    # "Datos de Hoy": PV, carga, descarga, entrada y salida de red.
    hoy = _by_unique_id(
        registry,
        (
            f"{plant_id}_plant_pv_energy_today",
            f"{plant_id}_plant_load_energy_today",
            f"{plant_id}_plant_battery_charging_today",
            f"{plant_id}_plant_battery_discharge_today",
            f"{plant_id}_plant_grid_import_today",
            f"{plant_id}_plant_grid_export_today",
        ),
    )
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
    stats = _by_unique_id(
        registry,
        (
            f"{plant_id}_plant_pv_energy_month",
            f"{plant_id}_plant_pv_energy_total",
        ),
    )
    if stats:
        cards.append(
            {
                "type": "entities",
                "title": "Datos estadísticos",
                "show_header_toggle": False,
                "entities": stats,
            }
        )

    # El estado de carga de la bateria. Es una entidad del dispositivo de
    # bateria, cuyo id empieza por el nombre de la planta, no por su id.
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
                "severity": {"green": 40, "yellow": 20, "red": 0},
            }
        )

    # La potencia de hoy, en su grafico.
    power = _by_unique_id(registry, (f"{plant_id}_plant_pv_power",))
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
    total = _by_unique_id(registry, (f"{plant_id}_plant_pv_energy_total",))
    if total:
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Generación (acumulado)",
                "entities": [total[0]],
                "chart_type": "bar",
                "period": "day",
                "days_to_show": 7,
            }
        )
        cards.append(
            {
                "type": "statistics-graph",
                "title": "Generación (mensual)",
                "entities": [total[0]],
                "chart_type": "bar",
                "period": "month",
                "days_to_show": 365,
            }
        )

    return cards


def _summary_cards(known: set[str], registry: dict[str, str]) -> list[dict[str, Any]]:
    """Build the cards of the summary page."""
    totals = _by_unique_id(
        registry,
        (
            "felicity_solar_total_pv_energy_all_plants",
            "felicity_solar_total_grid_import_all_plants",
            "felicity_solar_total_grid_export_all_plants",
            "felicity_solar_total_battery_charging_all_plants",
            "felicity_solar_total_battery_discharge_all_plants",
        ),
    )
    cards: list[dict[str, Any]] = []
    # El selector de fechas del que leen las tarjetas de energia.
    cards.append({"type": "energy-date-selection"})
    if totals:
        cards.append(
            {
                "type": "entities",
                "title": "Totales (todas las plantas)",
                "show_header_toggle": False,
                "entities": totals,
            }
        )
    power = _by_unique_id(registry, ("felicity_solar_total_pv_power_all_plants",))
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
    # El flujo de potencia en tiempo real, el equivalente al "Descripcion
    # general" de la app oficial.
    cards.append(
        {
            "type": "power-sankey",
            "title": "Flujo de energía en tiempo real",
        }
    )
    return cards


def build_dashboards(
    known: set[str], registry: dict[str, str], plant_ids: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Build the configuration of the dashboard.

    A single dashboard with one **view per plant**: Home Assistant shows the
    views as tabs of the same page.
    """
    views: list[dict[str, Any]] = [
        {
            "title": "Resumen",
            "path": "resumen",
            "type": "masonry",
            "cards": _summary_cards(known, registry),
        }
    ]
    for title, prefix, slug in PLANTS:
        plant_id = plant_ids.get(title)
        if plant_id is None:
            print(f"  ! no se encontro la planta {title}")
            continue
        views.append(
            {
                "title": title,
                "path": slug,
                "type": "masonry",
                "cards": _plant_cards(plant_id, prefix, known, registry),
            }
        )
    return {
        "felicity-solar": {
            "title": "Felicity Solar",
            "views": views,
        }
    }


async def _states(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    """Return the states of the instance, keyed by entity id."""
    async with session.get(f"{url}/api/states") as response:
        return {state["entity_id"]: state for state in await response.json()}


async def _entities(session: aiohttp.ClientSession, url: str) -> set[str]:
    """Return the entity ids of the instance."""
    return set(await _states(session, url))


async def _registry(session: aiohttp.ClientSession, url: str, token: str) -> dict[str, str]:
    """Return the unique id -> entity id map of the instance."""
    ws_url = url.replace("http://", "ws://").replace("https://", "wss://")
    async with session.ws_connect(f"{ws_url}/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        await ws.receive_json()
        await ws.send_json({"id": 1, "type": "config/entity_registry/list"})
        response = await ws.receive_json()
    entries = response.get("result") or []
    return {
        str(entry["unique_id"]): str(entry["entity_id"])
        for entry in entries
        if entry.get("unique_id") and entry.get("entity_id")
    }


async def _delete_dashboard(ws: aiohttp.ClientWSMessage, dashboard_id: str, next_id: int) -> None:
    """Delete a dashboard, if it exists.

    The first versions of this page created one dashboard per plant; they
    are all replaced by the views of the single "Felicity Solar" page.
    """
    await ws.send_json({"id": next_id, "type": "lovelace/dashboards/list"})
    existing = await ws.receive_json()
    if not any(d.get("id") == dashboard_id for d in existing.get("result", [])):
        return
    await ws.send_json(
        {
            "id": next_id + 1,
            "type": "lovelace/dashboards/delete",
            "dashboard_id": dashboard_id,
        }
    )
    await ws.receive_json()
    print(f"  {dashboard_id:26} borrado (dashboard antiguo)")


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
        states = await _states(session, url)
        registry = await _registry(session, url, token)
        plant_ids = _plant_ids(registry, states)
        dashboards = build_dashboards(known, registry, plant_ids)
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
            for old_id in ("felicity_solar_antares", "felicity_solar_antupiren"):
                await _delete_dashboard(ws, old_id, next_id)
                next_id += 1
            for url_path, spec in dashboards.items():
                result, next_id = await _save_dashboard(ws, url_path, spec["title"], spec, next_id)
                print(f"  {url_path:26} {result}")

    print(f"\nAbre: {url.rstrip('/')}/felicity-solar")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
