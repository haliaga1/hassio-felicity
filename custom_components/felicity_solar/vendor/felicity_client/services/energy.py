"""Energy flow operations."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from ..http import FelicityHTTP
from ..models.energy import EnergyFlow

_LOGGER = logging.getLogger(__name__)

__all__ = ["EnergyService"]

#: The path of the power series of a plant.
STORAGE_SERIES_PATH = "/storageRealtimeData/chart_storageRealtimeData_mate"

#: The minutes between two samples of the power series.
SAMPLE_MINUTES = 5


class EnergyService:
    """Reads the instantaneous energy flows of a plant."""

    def __init__(self, http: FelicityHTTP) -> None:
        self._http = http

    async def get_energy_flow(self, device_sn: str, plant_id: str) -> EnergyFlow:
        """Return the current energy flow for a device within a plant."""
        data = await self._http.get(
            "/device/get_energy_flow2",
            params={"deviceSn": device_sn, "plantId": plant_id},
        )
        if not isinstance(data, Mapping):
            raise ValueError(f"unexpected energy flow payload for {device_sn}")
        return EnergyFlow.from_payload(data)

    async def get_storage_series(self, plant_id: str) -> dict[str, list[float]]:
        """Return the power series of a plant, in watts, keyed by field.

        The API returns the last days of the installation, sampled every
        five minutes. The vendor's daily counters come empty for the
        battery, so this series is the only source of its energy.
        """
        data = await self._http.post(
            STORAGE_SERIES_PATH,
            json={"plantId": plant_id, "dateType": 1, "language": "en_US"},
        )
        if not isinstance(data, Mapping):
            raise ValueError(f"unexpected power series payload for {plant_id}")
        series: dict[str, list[float]] = {}
        for serie in data.get("storageMateDTOS") or []:
            field = serie.get("field")
            if not field:
                continue
            values: list[float] = []
            for value in serie.get("data") or []:
                try:
                    values.append(float(value) if value not in (None, "") else 0.0)
                except (TypeError, ValueError):
                    values.append(0.0)
            series[field] = values
        return series


def series_energy(samples: Sequence[float], sign: int = 1) -> float:
    """Return the energy of a power series, in kWh.

    The samples are five minutes apart, so the energy of one of them is the
    power times a twelfth of an hour. A negative sign takes the samples as
    they come, which is what a discharge needs.
    """
    total = 0.0
    for value in samples:
        total += max(0.0, value * sign) * (SAMPLE_MINUTES / 60) / 1000
    return total
