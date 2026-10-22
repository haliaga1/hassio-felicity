#!/usr/bin/env python3
"""Backfill the recorder with the real history of the plants.

How the recorder stores an energy counter
-----------------------------------------

For a ``total_increasing`` sensor the recorder keeps, in the ``sum`` column,
the **value of the counter at the end of the hour**, and the consumption of a
period is the *difference* between the newest and the oldest of those values
(``recorder/statistic_during_period`` computes exactly that ``change``).

Two consequences drive this script:

* the imported history has to be the **cumulative value** of the counter, not
  the production of the hour. Importing deltas would make the recorder
  carry the last delta over the hours without samples, and every total would
  drift;
* the values have to live in the **same scale** the recorder uses. The
  recorder accumulates the sum from the *first value it ever saw* of the
  sensor, so its sums are ``value - zero point``. The zero point is read
  from the recorder and every imported value is rebased with it.

The sources
-----------

1. **The historical records** (``/storageRealtimeData/list_storageRealtimeData_new``)
   are a paginated list of snapshots, one every 5 minutes, each holding the
   *cumulative* counters of that instant (``totalEnergy`` for the lifetime
   production, ``eLoadTotal`` for the lifetime consumption). The production
   of an hour is therefore the difference between two snapshots, with no
   integration error at all.

2. **The opening values.** The API publishes the month's and the year's
   totals (``monthPv``, ``yearPv``) but not their daily breakdown. Those
   totals are turned into the value the counter had when the period started,
   written in the hour *before* it, so the difference with the newest value
   is exactly the figure the API publishes::

       this month = (value now) - (value at the start of the month)
                  = monthPv

   Today and the last seven days come from the detail alone, and are exact.

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
import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import aiohttp

#: Minutes between two samples of the FSolar history.
SAMPLE_MINUTES = 5

#: Samples of a full day (24 h / 5 min).
SAMPLES_PER_DAY = 24 * 60 // SAMPLE_MINUTES

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

#: The aggregate statistics: the suffix of the plant statistic they add up
#: and the aggregate they feed.
AGGREGATE_SERIES: tuple[tuple[str, str], ...] = (
    ("_plant_pv_energy_total", "felicity_solar_total_pv_energy_all_plants"),
    ("_plant_grid_import_total", "felicity_solar_total_grid_import_all_plants"),
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


def _hourly_values(
    records: list[dict[str, Any]], field: str, tz: timezone
) -> tuple[dict[datetime, float], float]:
    """Return the value of a counter at the end of every hour, and its first value.

    The recorder stores, for a ``total_increasing`` sensor, the value of the
    counter at the end of the hour in the ``sum`` column: the consumption of
    a period is the difference between the newest and the oldest of those
    values.
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

    values: dict[datetime, float] = {}
    for moment, value in points:
        values[moment.replace(minute=0, second=0, microsecond=0)] = value
    if not values:
        return {}, 0.0
    return values, points[0][1]


def _productions(values: dict[datetime, float], first_value: float) -> dict[datetime, float]:
    """Return the energy produced in each hour."""
    hours = sorted(values)
    previous = first_value
    result: dict[datetime, float] = {}
    for hour in hours:
        result[hour] = max(0.0, values[hour] - previous)
        previous = values[hour]
    return result


def _openings(
    values: dict[datetime, float],
    first_value: float,
    productions: dict[datetime, float],
    month_total: float | None,
    year_total: float | None,
    tz: timezone,
) -> dict[datetime, float]:
    """Return the value the counter had when the month and the year started.

    The opening is written in the hour **before** the period starts, so the
    recorder finds it as the oldest sum of the period, and the difference
    with the newest one is exactly the production of the period::

        this month = (value now) - (value at the start of the month)
                   = monthPv

    The value at the start of the period is the value of the counter at the
    beginning of the detail, minus what was produced before the detail
    inside the period.
    """
    openings: dict[datetime, float] = {}
    if not values:
        return openings

    hours = sorted(values)
    local = hours[0].astimezone(tz)
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    detail_total = max(0.0, values[hours[-1]] - first_value)
    detail_month = sum(
        production for hour, production in productions.items() if hour >= month_start
    )

    if month_total is not None:
        value = first_value - (month_total - detail_month)
        # La hora anterior al periodo: es la fila mas antigua del periodo
        # para el recorder. Y la primera hora del periodo, que el recorder
        # usaria como valor inicial si faltara la anterior.
        openings[month_start - timedelta(hours=1)] = value
        openings[month_start] = value
    if year_total is not None:
        value = first_value - (year_total - detail_total)
        openings[year_start - timedelta(hours=1)] = value
        openings[year_start] = value
    return openings


def _counter_values(productions: dict[datetime, float], live_value: float) -> dict[datetime, float]:
    """Return the trajectory of a counter the integration accumulates itself.

    The integration turns the daily counters of the API into lifetime ones,
    so its counter only knows what happened since it started running. The
    series is anchored to the current value of the sensor, so the imported
    history ends exactly where the live data begins.
    """
    hours = sorted(productions)
    accumulated = 0.0
    values: dict[datetime, float] = {}
    for hour in hours:
        accumulated += productions[hour]
        values[hour] = accumulated
    if not values:
        return values
    offset = live_value - accumulated
    return {hour: max(0.0, value + offset) for hour, value in values.items()}


def _zero_openings(hourly: dict[datetime, float], tz: timezone) -> dict[datetime, float]:
    """Return the opening values of a counter that did not exist before.

    The counters the integration accumulates itself only know what happened
    since it started running, so their value at the beginning of the month
    and of the year is zero.
    """
    if not hourly:
        return {}
    local = min(hourly).astimezone(tz)
    month_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return {
        month_start - timedelta(hours=1): 0.0,
        month_start: 0.0,
        year_start - timedelta(hours=1): 0.0,
        year_start: 0.0,
    }


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


async def _states(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    """Return the states of the instance, keyed by entity id."""
    async with session.get(f"{url}/api/states") as response:
        return {state["entity_id"]: state for state in await response.json()}


async def _websocket(session: aiohttp.ClientSession, token: str, command: dict) -> Any:
    """Run one command in the websocket API of Home Assistant."""
    ws_url = os.environ["HA_URL"].replace("http://", "ws://").replace("https://", "wss://")
    async with session.ws_connect(f"{ws_url}/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        await ws.receive_json()
        await ws.send_json({"id": 1, **command})
        response = await ws.receive_json()
    if not response.get("success"):
        raise RuntimeError(response.get("error") or "the command failed")
    return response.get("result")


async def _recorder_base(
    session: aiohttp.ClientSession, token: str, statistic_id: str
) -> float | None:
    """Return the zero point the recorder uses for a sensor.

    The recorder accumulates the sum of a ``total_increasing`` sensor from the
    first value it ever saw, so the sums it stores are the value of the
    counter minus that zero point. The imported history has to use the same
    zero point, or the difference between the oldest and the newest sum
    would not be the production of the period.
    """
    now = datetime.now(UTC)
    for period, start in (("5minute", now - timedelta(hours=6)), ("hour", now - timedelta(days=3))):
        result = await _websocket(
            session,
            token,
            {
                "type": "recorder/statistics_during_period",
                "statistic_ids": [statistic_id],
                "start_time": start.isoformat(),
                "end_time": now.isoformat(),
                "period": period,
            },
        )
        rows = result.get(statistic_id) or []
        for row in reversed(rows):
            if row.get("sum") is None or row.get("state") is None:
                continue
            return float(row["state"]) - float(row["sum"])
    return None


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
    await _websocket(
        session,
        token,
        {
            "type": "recorder/import_statistics",
            "metadata": metadata,
            "stats": stats,
        },
    )
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
        states = await _states(session, ha_url)

        from felicity_client import FelicityClient

        async with FelicityClient(email, password) as client:
            plants = await client.list_plants()

        #: statistic id -> (the value of the counter at the end of the hour)
        absolute: dict[str, dict[datetime, float]] = {}
        #: statistic id -> (the value the counter had at the start of a period)
        openings: dict[str, dict[datetime, float]] = {}

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

            # --- El contador de por vida de la produccion y de la carga ----
            pv_values, pv_first = _hourly_values(records, "totalEnergy", tz)
            pv_productions = _productions(pv_values, pv_first)
            load_values, load_first = _hourly_values(records, "eLoadTotal", tz)
            load_productions = _productions(load_values, load_first)

            for name, values, first, productions, ref_month, ref_year in (
                (
                    "plant_pv_energy_total",
                    pv_values,
                    pv_first,
                    pv_productions,
                    month_total,
                    year_total,
                ),
                (
                    "plant_load_energy_total",
                    load_values,
                    load_first,
                    load_productions,
                    load_month_total,
                    load_year_total,
                ),
            ):
                if not values:
                    continue
                statistic = f"sensor.{prefix}_{name}"
                absolute[statistic] = values
                openings[statistic] = _openings(values, first, productions, ref_month, ref_year, tz)

            # --- Los contadores que acumula la propia integracion ---------
            for field, statistic_name, _group, sign in SERIES:
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
                live = states.get(statistic, {}).get("state")
                try:
                    live_value = float(live)
                except (TypeError, ValueError):
                    live_value = sum(hourly.values())
                absolute[statistic] = _counter_values(hourly, live_value)
                openings[statistic] = _zero_openings(hourly, tz)

        # --- Los agregados: la suma de las plantas ------------------------
        for suffix, statistic_name in AGGREGATE_SERIES:
            statistic = f"sensor.{statistic_name}"
            merged: dict[datetime, float] = {}
            merged_openings: dict[datetime, float] = {}
            for plant_statistic, values in absolute.items():
                if not plant_statistic.endswith(suffix):
                    continue
                for hour, value in values.items():
                    merged[hour] = merged.get(hour, 0.0) + value
                for hour, value in openings.get(plant_statistic, {}).items():
                    merged_openings[hour] = merged_openings.get(hour, 0.0) + value
            if merged:
                absolute[statistic] = merged
                openings[statistic] = merged_openings

        # --- La importacion, con el cero del recorder ----------------------
        for statistic, values in absolute.items():
            base = await _recorder_base(session, ha_token, statistic)
            if base is None:
                print(f"  {statistic}: el recorder no tiene datos, se omite")
                continue
            sums = {hour: value - base for hour, value in values.items()}
            states_of = dict(values)
            for hour, value in openings.get(statistic, {}).items():
                sums[hour] = value - base
                states_of[hour] = value

            # La comprobacion: el total del mes y del ano tienen que ser los
            # que publica el API.
            hours = sorted(sums)
            checks = ""
            if hours:
                newest = values[hours[-1]]
                for label, opening in openings.get(statistic, {}).items():
                    if label.hour != 0:
                        continue
                    total = newest - opening
                    checks += f"  {label:%m-%d}={total:.2f}"
            if args.dry_run:
                print(f"  {statistic:56} {len(sums):3} h  cero={base:10.2f}{checks}")
                continue

            count = await _import_statistics(session, ha_token, statistic, sums, states_of)
            first = min(sums) if sums else None
            last = max(sums) if sums else None
            span = f"{first:%m-%d %H} -> {last:%m-%d %H}" if first else ""
            print(f"  {statistic:56} {count:3} h  cero={base:10.2f}  {span}{checks}")

    return 0


def _as_float(value: Any) -> float | None:
    """Return a float, or None when the value is missing."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
