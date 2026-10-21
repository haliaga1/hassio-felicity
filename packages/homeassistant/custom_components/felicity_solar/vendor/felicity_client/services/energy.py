"""Energy flow operations."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from ..http import FelicityHTTP
from ..models.energy import EnergyFlow

_LOGGER = logging.getLogger(__name__)

__all__ = ["EnergyService"]


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
