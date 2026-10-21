"""Plant-level operations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..http import FelicityHTTP
from ..models.common import Plant

_LOGGER = logging.getLogger(__name__)

__all__ = ["PlantService", "extract_list"]

#: Key used by the backend for the rows of a paginated response.
_LIST_KEYS = ("dataList", "list", "records", "rows", "content")


def extract_list(data: Any) -> tuple[list[Mapping[str, Any]], int]:
    """Normalise the many shapes a paged FSolar response can take.

    Returns the rows and the reported total (``-1`` when the backend does not
    report one).
    """
    if data is None:
        return [], 0
    if isinstance(data, list):
        rows = [item for item in data if isinstance(item, Mapping)]
        return rows, len(rows)
    if not isinstance(data, Mapping):
        return [], 0

    for key in _LIST_KEYS:
        candidate = data.get(key)
        if isinstance(candidate, list):
            rows = [item for item in candidate if isinstance(item, Mapping)]
            total = data.get("total")
            return rows, int(total) if isinstance(total, int) else len(rows)

    return [], 0


class PlantService:
    """Reads the plants attached to an account."""

    def __init__(self, http: FelicityHTTP) -> None:
        self._http = http

    async def list_plants(self, *, page_size: int = 50) -> list[Plant]:
        """Return every plant visible to the account.

        The backend paginates; this walks the pages until the reported total
        is reached so that accounts with several installations are not
        silently truncated.
        """
        plants: list[Plant] = []
        seen: set[str] = set()
        page = 1

        while True:
            data = await self._http.post(
                "/plant/list_plant",
                json={"pageNum": page, "pageSize": page_size},
            )
            rows, total = extract_list(data)
            if not rows:
                break

            for row in rows:
                plant = Plant.from_payload(row)
                if not plant.id or plant.id in seen:
                    continue
                seen.add(plant.id)
                plants.append(plant)

            _LOGGER.debug("Loaded %s plant(s) on page %s", len(rows), page)
            if len(plants) >= total or len(rows) < page_size:
                break
            page += 1

        _LOGGER.info("Found %s plant(s) for the account", len(plants))
        return plants

    async def get_plant(self, plant_id: str) -> Plant:
        """Return the details of a single plant."""
        data = await self._http.post("/plant/plantDetails", json={"id": plant_id})
        if not isinstance(data, Mapping):
            raise ValueError(f"unexpected plant details payload for {plant_id}")
        return Plant.from_payload(data)
