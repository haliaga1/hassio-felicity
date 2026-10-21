"""Alert and warning operations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..http import FelicityHTTP
from ..models.alerts import Alert, AlertGroup
from .plants import extract_list

_LOGGER = logging.getLogger(__name__)

__all__ = ["AlertService"]


class AlertService:
    """Reads the warnings raised by the devices of an account."""

    def __init__(self, http: FelicityHTTP) -> None:
        self._http = http

    async def list_alerts(
        self,
        device_sn: str | None = None,
        *,
        days: int = 30,
        page_size: int = 50,
    ) -> list[Alert]:
        """Return the warnings of the account, optionally for a single device.

        The endpoint requires a page number, a page size and a date range;
        omitting them is answered with a validation error, not with an empty
        list.
        """
        payload: dict[str, Any] = {
            "pageNum": 1,
            "pageSize": page_size,
            "leftDate": _date_offset(-abs(days)),
            "rightDate": _date_offset(0),
        }
        if device_sn:
            payload["deviceSn"] = device_sn

        data = await self._http.post("/device/device_warring_list", json=payload)
        rows, _ = extract_list(data)
        alerts = [Alert.from_payload(row) for row in rows]
        _LOGGER.debug("Loaded %s alert(s)", len(alerts))
        return alerts

    async def list_alert_groups(self, device_sn: str | None = None) -> list[AlertGroup]:
        """Return the warnings grouped by device."""
        payload: dict[str, Any] = {
            "pageNum": 1,
            "pageSize": 50,
            "leftDate": _date_offset(-30),
            "rightDate": _date_offset(0),
        }
        if device_sn:
            payload["deviceSn"] = device_sn

        data = await self._http.post("/device/warring/group", json=payload)
        rows, _ = extract_list(data)
        groups = [AlertGroup.from_payload(row) for row in rows]
        _LOGGER.debug("Loaded %s alert group(s)", len(groups))
        return groups

    async def acknowledge(self, alert_id: str, status: int = 1) -> bool:
        """Mark an alert as seen.

        ``/deviceWarning/update_warn_status`` mutates the backend, so this is
        the only write operation in the client and it is opt-in.
        """
        await self._http.post(
            "/deviceWarning/update_warn_status",
            json={"id": alert_id, "status": status},
        )
        _LOGGER.info("Marked the alert %s as %s", alert_id, "seen" if status else "unseen")
        return True


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """Narrow an arbitrary payload to a mapping."""
    return value if isinstance(value, Mapping) else {}


def _date_offset(days: int) -> str:
    """Return a date offset from today, as ``YYYY-MM-DD HH:MM:SS``.

    The endpoint rejects a bare ``YYYY-MM-DD``: it answers
    ``leftDate: must not be null`` even when the field is present.
    """
    from datetime import datetime, timedelta

    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
