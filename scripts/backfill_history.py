#!/usr/bin/env python3
"""Backfill the recorder with the real history of the plants, and the
opening balances of the counters that predate the integration.

Two sources are used, and both are exact:

1. **The historical records** (``/storageRealtimeData/list_storageRealtimeData_new``)
   are a paginated list of snapshots, one every 5 minutes, each holding the
   *cumulative* counters of that instant (``totalEnergy`` for the lifetime
   production, ``eLoadTotal`` for the lifetime consumption). The production
   of an hour is therefore the difference between two snapshots, with no
   integration error at all.

2. **The opening balances.** The API publishes the month's and the year's
   totals (``monthPv``, ``yearPv``) but not their daily breakdown. Those
   totals are turned into a single *opening* statistic at the first hour of
   the period, so the Energy Dashboard shows the real figure for "this
   month" and "this year" instead of only the days the integration has been
   running.

The openings are nested and computed as residuals, from the longest period
to the shortest, so every window of the dashboard stays consistent::

    year  opening = yearPv  - detail - month opening
    month opening = monthPv - detail
    detail         = the exact hourly production

    today    = detail of today                       (exact)
    7 days   = detail of the last 7 days             (exact)
    this month = month opening + detail of the month  (= monthPv)
    this year  = year opening + month opening + detail (= yearPv)

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
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

#: Minutes between two samples of the FSolar history.
SAMPLE_MINUTES = 5

#: Samples of a full day (24 h / 5 min).
SAMPLES_PER_DAY = 24 * 60 // SAMPLE_MINUTES

#: The statistic of the Energy Dashboard that consumes the production.
PLANT_STATISTIC = "plant_pv_energy_total"
AGGREGATE_STATISTIC = "felicity_solar_total_pv_energy_all_plants"

#: The series of the FSolar history -> the statistic it feeds.
#:
#: ``sign`` is applied to the samples: the battery reports the discharge as a
#: negative power, but the counter of the discharged energy has to grow.
SERIES: tuple[tuple[str, str, str, int], ...] = (
    ("pvElectricity", "plant_pv_energy_total", "pv", 1),
    ("backupLoad", "plant_load_energy_total", "load", 1),
    ("batteryCharging", "plant_battery_charging_total", "battery", 1),
    ("batteryDischarge", "plant_battery_discharge_total", "battery", -1),
    ("gridInput", "plant_grid_import_total", "grid", 1),
    ("feedOutput", "plant_grid_export_total", "grid", 1),
)

#: The aggregate statistics, per series.
AGGREGATE_SERIES: tuple[tuple[str, str], ...] = (
    ("pv", "felicity_solar_total_pv_energy_all_plants"),
    ("grid", "felicity_solar_total_grid_import_all_plants"),
)

API_URL = "https://shine-api.felicitysolar.com"
CHART_PATH = "/storageRealtimeData/chart_storageRealtimeData_mate"
RECORDS_PATH = "/storageRealtimeData/list_storageRealtimeData_new"
PLANT_DETAILS_PATH = "/plant/plantDetails"


async def _login(email: str, password: str) -> dict[str, str]:
    """Log in to FSolar and return the request headers."""
    from felicity_client import FelicityClient

    async with FelicityClient(email, password) as client:
        token = await client.auth.get_token()
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": token,
        "content-type": "application/json",
        "lang": "en_US",
        "source": "WEB",
        "Node": "INT",
    }


async def _post(
    session: aiohttp.ClientSession, headers: dict[str, str], path: str, payload: dict
) -> dict[str, Any]:
    """POST to the FSolar API and return the ``data`` member."""
    async with session.post(f"{API_URL}{path}", headers=headers, json=payload) as response:
        body = await response.json()
    return body.get("data") or {}


async def _fetch_records(
    session: aiohttp.ClientSession, headers: dict[str, str], plant_id: str
) -> list[dict[str, Any]]:
    """Return every historical record of a plant, oldest first."""
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        data = await _post(
            session,
            headers,
            RECORDS_PATH,
            {"plantId": plant_id, "dateType": 1, "pageNum": page, "pageSize": 300},
        )
        items = data.get("dataList") or []
        records.extend(items)
        total = int(data.get("total") or 0)
        if not items or len(records) >= total or page > 30:
            break
        page += 1
    return records


async def _fetch_series(
    session: aiohttp.ClientSession, headers: dict[str, str], plant_id: str
) -> dict[str, list[float]]:
    """Return the power series of a plant, in watts, keyed by field."""
    data = await _post(
        session, headers, CHART_PATH, {"plantId": plant_id, "dateType": 1, "language": "en_US"}
    )
    series: dict[str, list[float]] = {}
    for serie in data.get("storageMateDTOS", []):
        field = serie.get("field")
        if not field:
            continue
        series[field] = [
            float(value) if value not in (None, "") else 0.0 for value in serie.get("data", [])
        ]
    return series


def _hourly_from_records(
    records: list[dict[str, Any]], field: str, tz: timezone, resets_daily: bool = False
) -> tuple[dict[datetime, float], dict[datetime, float]]:
    """Return the hourly production and the hourly value of a counter.

    The production is computed **between consecutive records**, so no energy
    is lost in the gap between two hours. A counter that goes down has been
    reset (the daily ones reset at midnight), and then the whole current
    value is the production of that interval.
    """
    points: list[tuple[datetime, float]] = []
    for record in records:
        raw = record.get(field)
        stamp = record.get("dataTime")
        if raw in (None, "") or not stamp:
            continue
        try:
            moment = datetime.fromisoformat(str(stamp)).astimezone(tz)
            value = float(raw)
        except (TypeError, ValueError):
            continue
        points.append((moment, value))
    points.sort()

    sums: dict[datetime, float] = {}
    states: dict[datetime, float] = {}
    previous: tuple[datetime, float] | None = None
    for moment, value in points:
        hour = moment.replace(minute=0, second=0, microsecond=0)
        if previous is not None:
            delta = value - previous[1]
            if delta < 0:
                if not resets_daily:
                    # Un contador de por vida que baja significa que se
                    # cambio el equipo: la produccion de ese intervalo se
                    # desconoce, asi que no se cuenta nada.
                    previous = (moment, value)
                    states[hour] = value
                    continue
                # El contador diario se reinicio a medianoche: todo el
                # valor actual es la produccion desde el ultimo reinicio.
                delta = value
            sums[hour] = sums.get(hour, 0.0) + max(0.0, delta)
        states[hour] = value
        previous = (moment, value)
    return sums, states


def _day_starts(samples: list[float], now: datetime, tz: timezone) -> list[tuple[datetime, int]]:
    """Return the (start, first index) of every day present in the series."""
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
    samples: list[float], day_start: datetime, day_start_index: int, sign: int = 1
) -> dict[datetime, float]:
    """Return the kWh of each hour of a day, from the power series."""
    result: dict[datetime, float] = {}
    for hour in range(24):
        start = hour * (60 // SAMPLE_MINUTES)
        chunk = samples[day_start_index + start : day_start_index + start + (60 // SAMPLE_MINUTES)]
        if not chunk:
            continue
        kwh = sum(max(0.0, value * sign) for value in chunk) * (SAMPLE_MINUTES / 60) / 1000
        result[day_start + timedelta(hours=hour)] = kwh
    return result


def _openings(
    sums: dict[datetime, float],
    states: dict[datetime, float],
    month_total: float | None,
    year_total: float | None,
    tz: timezone,
) -> tuple[dict[datetime, float], dict[datetime, float]]:
    """Compute the opening balances of the month and the year.

    They are nested residuals, from the longest period to the shortest, so
    every window of the Energy Dashboard stays consistent.
    """
    openings_sum: dict[datetime, float] = {}
    openings_state: dict[datetime, float] = {}
    if not sums:
        return openings_sum, openings_state, None, 0.0, 0.0

    hours = sorted(sums)
    first_hour = hours[0]
    first_value = states.get(first_hour, 0.0)

    local = first_hour.astimezone(tz)
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    detail_month = sum(v for k, v in sums.items() if k >= month_start)
    detail_year = sum(sums.values())

    month_opening = None
    if month_total is not None:
        month_opening = month_total - detail_month
    year_opening = None
    if year_total is not None:
        year_opening = year_total - detail_year - (month_opening or 0.0)

    if month_opening is not None:
        openings_sum[month_start] = month_opening
        # El valor del contador al inicio del mes.
        openings_state[month_start] = first_value - detail_month
    if year_opening is not None:
        openings_sum[year_start] = year_opening
        openings_state[year_start] = first_value - detail_year - (month_opening or 0.0)
    return openings_sum, openings_state, month_start, detail_month, detail_year


async def _import_statistics(
    session: aiohttp.ClientSession,
    token: str,
    statistic_id: str,
    sums: dict[datetime, float],
    states: dict[datetime, float] | None = None,
) -> int:
    """Import the hourly statistics of one sensor."""
    stats: list[dict[str, Any]] = []
    for start, value in sorted(sums.items()):
        if value <= 0:
            continue
        entry: dict[str, Any] = {"start": start.isoformat(), "sum": round(value, 4)}
        if states and start in states:
            entry["state"] = round(states[start], 4)
        stats.append(entry)
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


def _plant_prefix(plant_name: str) -> str:
    """Return the entity prefix of a plant, as the integration names it."""
    normalized = unicodedata.normalize("NFKD", plant_name)
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    return "-".join(part for part in without_accents.lower().split() if part)


def _tz_offset(name: str) -> float:
    """Return the UTC offset in hours of a timezone name."""
    try:
        from zoneinfo import ZoneInfo

        offset = ZoneInfo(name).utcoffset(datetime.now())
        return (offset.total_seconds() / 3600) if offset else 0.0
    except Exception:  # noqa: BLE001 - a missing timezone must not stop the backfill
        return 0.0


async def _load_year_total(client: Any, plant_id: str) -> float | None:
    """The yearly AC output of the plant's inverter."""
    try:
        devices = await client.list_devices(plant_id=plant_id)
    except Exception:  # noqa: BLE001 - a missing reference is not fatal
        return None
    for device in devices:
        if device.product_type.name != "INVERTER":
            continue
        try:
            snapshot = await client.get_snapshot(device.serial_number)
        except Exception as exc:  # noqa: BLE001 - a missing reference is not fatal
            print(f"    no se pudo leer el total anual de carga: {exc}")
            continue
        if snapshot.ac_in.energy_total_kwh is not None:
            return snapshot.ac_in.energy_total_kwh
    return None


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

    fsolar_headers = await _login(email, password)
    headers = {"Authorization": f"Bearer {ha_token}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{ha_url}/api/config") as response:
            ha_config = await response.json()
        tz = timezone(timedelta(hours=_tz_offset(ha_config.get("time_zone", "UTC"))))
        now = datetime.now(tz)

        from felicity_client import FelicityClient

        async with FelicityClient(email, password) as client:
            plants = await client.list_plants()

        aggregate: dict[str, dict[datetime, float]] = {key: {} for key, _ in AGGREGATE_SERIES}
        for plant in plants:
            async with aiohttp.ClientSession() as fs:
                records = await _fetch_records(fs, fsolar_headers, plant.id)
                series = await _fetch_series(fs, fsolar_headers, plant.id)
                details = await _post(fs, fsolar_headers, PLANT_DETAILS_PATH, {"plantId": plant.id})
            if not records:
                print(f"  {plant.name}: sin registros, se omite")
                continue

            prefix = _plant_prefix(plant.name)
            month_total = _as_float(details.get("monthPv"))
            year_total = _as_float(details.get("yearPv")) or _as_float(details.get("accPv"))
            # La carga tiene su propia referencia anual: el total anual de
            # salida en CA del inversor (eLoadYear). El API no publica un
            # total mensual de carga.
            load_month_total = None
            load_year_total = await _load_year_total(client, plant.id)

            # --- Produccion: la de los registros historicos (exacta) --------
            # La produccion del PV sale del contador diario (ePvToday) y el
            # nivel del contador de por vida (totalEnergy).
            pv_sums, _ = _hourly_from_records(records, "ePvToday", tz, resets_daily=True)
            _, pv_states = _hourly_from_records(records, "totalEnergy", tz)
            # La carga se mide con su contador de por vida.
            load_sums, load_states = _hourly_from_records(records, "eLoadTotal", tz)

            for sums, states, name, ref_month, ref_year in (
                (pv_sums, pv_states, "plant_pv_energy_total", month_total, year_total),
                (
                    load_sums,
                    load_states,
                    "plant_load_energy_total",
                    load_month_total,
                    load_year_total,
                ),
            ):
                if not sums:
                    continue
                openings_sum, openings_state, month_start, detail_month, _ = _openings(
                    sums, states, ref_month, ref_year, tz
                )
                merged = {**openings_sum, **sums}
                merged_states = {**openings_state, **states}
                # El total del mes: la apertura del mes mas el detalle.
                # La apertura del ano queda fuera (es de enero).
                total_month = (
                    sum(v for k, v in merged.items() if k >= month_start)
                    if month_start is not None
                    else detail_month
                )
                statistic = f"sensor.{prefix}_{name}"
                if args.dry_run:
                    print(
                        f"  {plant.name:11} {name:24} {len(merged):3} h  "
                        f"mes={total_month:8.2f} kWh (API {month_total})"
                    )
                    continue
                count = await _import_statistics(
                    session, ha_token, statistic, merged, merged_states
                )
                print(
                    f"  {plant.name:11} {name:24} {count:3} h importadas en {statistic}  "
                    f"mes={total_month:.2f} kWh (API {month_total})"
                )
                if name == "plant_pv_energy_total":
                    for hour, value in merged.items():
                        aggregate["pv"][hour] = aggregate["pv"].get(hour, 0.0) + value

            # --- El resto de series: desde la serie de potencias -----------
            for field, statistic_name, group, sign in SERIES:
                if field in ("pvElectricity", "backupLoad"):
                    continue
                samples = series.get(field)
                if not samples:
                    continue
                days = _day_starts(samples, now, tz)
                hourly: dict[datetime, float] = {}
                for day_start, index in days:
                    for hour_start, kwh in _hourly_production(
                        samples, day_start, index, sign
                    ).items():
                        hourly[hour_start] = hourly.get(hour_start, 0.0) + kwh
                statistic = f"sensor.{prefix}_{statistic_name}"
                if args.dry_run:
                    print(f"  {plant.name:11} {statistic_name:24} {len(hourly):3} h")
                    continue
                count = await _import_statistics(session, ha_token, statistic, hourly)
                print(
                    f"  {plant.name:11} {statistic_name:24} {count:3} h importadas en {statistic}"
                )
                if group in aggregate:
                    for hour, value in hourly.items():
                        aggregate[group][hour] = aggregate[group].get(hour, 0.0) + value

        if not args.dry_run:
            for group, statistic_name in AGGREGATE_SERIES:
                bucket = aggregate.get(group)
                if not bucket:
                    continue
                statistic = f"sensor.{statistic_name}"
                count = await _import_statistics(session, ha_token, statistic, bucket)
                print(f"  {'':11} {statistic_name:24} {count:3} h importadas en {statistic}")

    return 0


def _as_float(value: Any) -> float | None:
    """Coerce a float, or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _month_start(hours: dict[datetime, float], tz: timezone) -> datetime:
    """The first instant of the month of the given hours."""
    first = min(hours)
    return first.astimezone(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
