"""Alert and warning model.

The FSolar backend exposes active warnings through
``POST /device/device_warring_list`` and ``POST /device/warring/group``, and
their history through the ``/historyWarning/*`` endpoints. The field names
below are best-effort; the raw payload is always preserved.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .._coerce import to_int, to_str

__all__ = ["Alert", "AlertGroup"]

#: Candidate field names, in priority order, for each logical attribute.
_TITLE_KEYS = ("warnTitle", "title", "warningName", "name", "faultName", "message")
_DESCRIPTION_KEYS = ("warnContent", "content", "description", "remark", "detail")
_SEVERITY_KEYS = ("warnLevel", "level", "severity", "grade", "levelName")
_STATUS_KEYS = ("status", "statusStr", "state", "warnStatus", "handleStatus")
_TIME_KEYS = ("createTime", "warnTime", "time", "eventTime", "happenTime")
_CODE_KEYS = ("warnCode", "code", "faultCode", "errorCode")
_DEVICE_KEYS = ("deviceSn", "sn", "deviceSN")


@dataclass(frozen=True, slots=True)
class Alert:
    """A single warning raised by a device."""

    id: str
    device_sn: str | None = None
    title: str | None = None
    description: str | None = None
    severity: str | None = None
    status: str | None = None
    code: str | None = None
    created_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Alert:
        """Build an alert from a warning record."""
        identifier = (
            to_str(payload.get("id"))
            or to_str(payload.get("warnId"))
            or to_str(payload.get("recordId"))
            or ""
        )
        return cls(
            id=identifier,
            device_sn=_first(payload, _DEVICE_KEYS),
            title=_first(payload, _TITLE_KEYS),
            description=_first(payload, _DESCRIPTION_KEYS),
            severity=_first(payload, _SEVERITY_KEYS),
            status=_first(payload, _STATUS_KEYS),
            code=_first(payload, _CODE_KEYS),
            created_at=_parse_time(payload),
            raw=dict(payload),
        )

    @property
    def is_active(self) -> bool | None:
        """Whether the alert is still active, or ``None`` when unknown."""
        if self.status is None:
            return None
        lowered = self.status.lower()
        if lowered in {"0", "false", "untreated", "pending", "active", "unhandled"}:
            return True
        if lowered in {"1", "true", "treated", "cleared", "closed", "resolved"}:
            return False
        return None


@dataclass(frozen=True, slots=True)
class AlertGroup:
    """A group of alerts, as returned by ``/device/warring/group``."""

    device_sn: str | None = None
    name: str | None = None
    count: int | None = None
    alerts: tuple[Alert, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> AlertGroup:
        """Build a group from a ``warring/group`` record."""
        nested = payload.get("dataList") or payload.get("list") or payload.get("warnList") or []
        alerts: list[Alert] = []
        if isinstance(nested, (list, tuple)):
            for item in nested:
                if isinstance(item, Mapping):
                    alerts.append(Alert.from_payload(item))
        return cls(
            device_sn=_first(payload, _DEVICE_KEYS),
            name=_first(payload, _TITLE_KEYS),
            count=to_int(payload.get("count")) if payload.get("count") is not None else len(alerts),
            alerts=tuple(alerts),
            raw=dict(payload),
        )


def _first(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty value among ``keys``."""
    for key in keys:
        value = to_str(payload.get(key))
        if value is not None:
            return value
    return None


def _parse_time(payload: Mapping[str, Any]) -> datetime | None:
    """Extract a timestamp from the first matching time field."""
    for key in _TIME_KEYS:
        raw = payload.get(key)
        if raw is None:
            continue
        epoch = to_int(raw)
        if epoch is not None and epoch > 0:
            # The backend mixes second and millisecond epochs.
            seconds = epoch / 1000 if epoch > 1_000_000_000 else epoch
            return datetime.fromtimestamp(seconds, tz=UTC)
        text = to_str(raw)
        if text is None:
            continue
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
    return None
