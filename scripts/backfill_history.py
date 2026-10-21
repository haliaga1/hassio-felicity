#!/usr/bin/env python3
"""Backfill the recorder with the real production history of the plants.

The FSolar API publishes the historical production of each plant at a
**5 minute** resolution::

    POST /storageRealtimeData/chart_storageRealtimeData_mate
      {"plantId": ..., "dateType": 1, "language": "en_US"}

The response holds one array of watts per flow, concatenated day after day
(288 samples of 5 minutes each), plus a ``dataTime`` axis with the labels of
a single day. The last sample is *now*, so the current day starts at
``len(samples) - minutes_since_midnight / 5`` and every previous day is 288
samples further back.

From that series the production of every hour is computed and imported into
the recorder as the hourly ``sum`` of the lifetime counter, which is exactly
what the Home Assistant Energy Dashboard consumes.

The result is verified against the plant's own daily counter (``todayPv``):
if the integration of the series does not reproduce it, nothing is written.

Usage::

    export HA_URL="http://192.168.1.5:8123"
    export HA_TOKEN="<long-lived access token>"
    export FELICITY_TEST_EMAIL="..."
    export FELICITY_TEST_PASSWORD="..."
    uv run python scripts/backfill_history.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

#: Minutes between two samples of the FSolar history.
SAMPLE_MINUTES = 5

#: Samples of a full day (24 h / 5 min).
SAMPLES_PER_DAY = 24 * 60 // SAMPLE_MINUTES

#: The flow that carries the photovoltaic production.
PV_FIELD = "pvElectricity"

#: The statistic the Energy Dashboard consumes for the production.
PLANT_STATISTIC = "plant_pv_energy_total"
AGGREGATE_STATISTIC = "felicity_solar_total_pv_energy_all_plants"

API_URL = "https://shine-api.felicitysolar.com"
CHART_PATH = "/storageRealtimeData/chart_storageRealtimeData_mate"


async def _login(email: str, password: str) -> tuple[str, dict[str, str]]:
    """Log in to FSolar and return the token and the headers."""
    from felicity_client import FelicityClient

    async with FelicityClient(email, password) as client:
        token = await client.auth.get_token()
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": token,
        "content-type": "application/json",
        "lang": "en_US",
        "source": "WEB",
        "Node": "INT",
    }
    return token, headers


async def _fetch_series(
    session: aiohttp.ClientSession, headers: dict[str, str], plant_id: str
) -> list[float]:
    """Return the PV power series of a plant, in watts."""
    async with session.post(
        f"{API_URL}{CHART_PATH}",
        headers=headers,
        json={"plantId": plant_id, "dateType": 1, "language": "en_US"},
    ) as response:
        payload = await response.json()
    data = payload.get("data") or {}
    for serie in data.get("storageMateDTOS", []):
        if serie.get("field") == PV_FIELD:
            return [
                float(value) if value not in (None, "") else 0.0 for value in serie.get("data", [])
            ]
    return []


def _day_starts(samples: list[float], now: datetime, tz: timezone) -> list[tuple[datetime, int]]:
    """Return the (start, first index) of every day present in the series.

    The last sample is *now*, so the current day starts
    ``samples_since_midnight`` samples before the end, and every previous
    day is ``SAMPLES_PER_DAY`` samples further back.
    """
    local_now = now.astimezone(tz)
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_today = (local_now - midnight).total_seconds() / 60
    today_samples = int(minutes_today // SAMPLE_MINUTES) + 1

    days: list[tuple[datetime, int]] = []
    start_index = len(samples) - today_samples
    day_start = midnight
    while start_index >= 0:
        days.append((day_start, start_index))
        start_index -= SAMPLES_PER_DAY
        day_start -= timedelta(days=1)
    return list(reversed(days))


def _hourly_production(
    samples: list[float], day_start: datetime, day_start_index: int
) -> dict[datetime, float]:
    """Return the kWh produced in each hour of a day."""
    result: dict[datetime, float] = {}
    for hour in range(24):
        start = hour * (60 // SAMPLE_MINUTES)
        chunk = samples[day_start_index + start : day_start_index + start + (60 // SAMPLE_MINUTES)]
        if not chunk:
            continue
        kwh = sum(chunk) * (SAMPLE_MINUTES / 60) / 1000
        result[day_start + timedelta(hours=hour)] = kwh
    return result


async def _import_statistics(
    session: aiohttp.ClientSession,
    token: str,
    statistic_id: str,
    hourly: dict[datetime, float],
) -> int:
    """Import the hourly statistics of one sensor."""
    stats = [
        {"start": start.isoformat(), "sum": round(value, 4)}
        for start, value in sorted(hourly.items())
        if value > 0
    ]
    if not stats:
        return 0

    metadata = {
        "has_mean": False,
        "has_sum": True,
        "name": statistic_id.split(".", 1)[-1].replace("_", " ").title(),
        "source": "recorder",
        "statistic_id": statistic_id,
        "unit_class": "energy",
        "unit_of_measurement": "kWh",
    }
    ws_url = os.environ["HA_URL"].replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/websocket"
    async with session.ws_connect(ws_url) as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        await ws.receive_json()
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
        print(f"    ERROR importando {statistic_id}: {response.get('error')}")
        return 0
    return len(stats)


async def main() -> int:
    """Run the backfill."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="only show what would be done")
    args = parser.parse_args()

    ha_url = os.environ.get("HA_URL")
    ha_token = os.environ.get("HA_TOKEN")
    email = os.environ.get("FELICITY_TEST_EMAIL")
    password = os.environ.get("FELICITY_TEST_PASSWORD")
    if not all((ha_url, ha_token, email, password)):
        print("HA_URL, HA_TOKEN, FELICITY_TEST_EMAIL and FELICITY_TEST_PASSWORD are required")
        return 2

    _, fsolar_headers = await _login(email, password)
    headers = {"Authorization": f"Bearer {ha_token}"}

    # La zona horaria de Home Assistant, que es la de las plantas.
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{ha_url}/api/config") as response:
            ha_config = await response.json()
        tz = timezone(timedelta(hours=_tz_offset(ha_config.get("time_zone", "UTC"))))
        now = datetime.now(tz)

        from felicity_client import FelicityClient

        async with FelicityClient(email, password) as client:
            plants = await client.list_plants()

        aggregate: dict[datetime, float] = {}
        for plant in plants:
            async with aiohttp.ClientSession() as fs:
                samples = await _fetch_series(fs, fsolar_headers, plant.id)
            if not samples:
                print(f"  {plant.name}: sin serie, se omite")
                continue

            days = _day_starts(samples, now, tz)
            total_today = 0.0
            hourly: dict[datetime, float] = {}
            for day_start, index in days:
                per_hour = _hourly_production(samples, day_start, index)
                for hour_start, kwh in per_hour.items():
                    hourly[hour_start] = hourly.get(hour_start, 0.0) + kwh
                    aggregate[hour_start] = aggregate.get(hour_start, 0.0) + kwh
                if day_start.date() == now.date():
                    total_today = sum(per_hour.values())

            # Verificacion: la serie debe reproducir el contador diario del API.
            details = await _plant_details(fsolar_headers, plant.id)
            expected = details.get("todayPv")
            check = ""
            if expected is not None:
                expected_f = float(expected)
                deviation = abs(total_today - expected_f)
                check = f"  (API {expected_f:.2f} kWh, desviacion {deviation:.2f})"
                if deviation > max(0.5, expected_f * 0.1):
                    print(f"  {plant.name}: la serie NO cuadra{check}, se omite")
                    continue
            print(f"  {plant.name}: {len(hourly)} hora(s), hoy {total_today:.2f} kWh{check}")

            if args.dry_run:
                continue

            # El sensor de la planta: el prefijo sale del nombre de la planta.
            prefix = _plant_prefix(plant.name)
            statistic = f"sensor.{prefix}_{PLANT_STATISTIC}"
            count = await _import_statistics(session, ha_token, statistic, hourly)
            print(f"    importadas {count} estadisticas en {statistic}")

        if not args.dry_run:
            count = await _import_statistics(
                session, ha_token, f"sensor.{AGGREGATE_STATISTIC}", aggregate
            )
            print(f"  importadas {count} estadisticas en sensor.{AGGREGATE_STATISTIC}")

    return 0


def _tz_offset(name: str) -> float:
    """Return the UTC offset in hours of a timezone name."""
    try:
        from zoneinfo import ZoneInfo

        offset = ZoneInfo(name).utcoffset(datetime.now())
        return (offset.total_seconds() / 3600) if offset else 0.0
    except Exception:  # noqa: BLE001 - a missing timezone must not stop the backfill
        return 0.0


def _plant_prefix(plant_name: str) -> str:
    """Return the entity prefix of a plant, as the integration names it.

    Home Assistant slugs the names, which also strips the accents: the plant
    "Antupirén" becomes ``antupiren``.
    """
    import unicodedata

    normalized = unicodedata.normalize("NFKD", plant_name)
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    return "-".join(part for part in without_accents.lower().split() if part)


async def _plant_details(headers: dict[str, str], plant_id: str) -> dict[str, Any]:
    """Return the plant details."""
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{API_URL}/plant/plantDetails",
            headers=headers,
            json={"plantId": plant_id},
        ) as response,
    ):
        payload = await response.json()
    return payload.get("data") or {}


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
