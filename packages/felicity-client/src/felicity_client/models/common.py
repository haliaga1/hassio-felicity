"""Shared model types: plants, devices and product categories."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .._coerce import to_int, to_str

__all__ = [
    "Device",
    "DeviceType",
    "Plant",
    "ProductType",
]


class ProductType(StrEnum):
    """The ``productTypeEnum`` discriminant returned by the snapshot endpoint."""

    INVERTER = "HIGH_FREQUENCY_INVERTER"
    BATTERY = "LITHIUM_BATTERY_PACK"
    CONTROLLER = "CONTROLLER"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def parse(cls, value: object) -> ProductType:
        """Map a raw ``productTypeEnum`` value to a member, never raising."""
        raw = to_str(value)
        if raw is None:
            return cls.UNKNOWN
        try:
            return cls(raw)
        except ValueError:
            return cls.UNKNOWN


#: Backwards-friendly alias.
DeviceType = ProductType


@dataclass(frozen=True, slots=True)
class Plant:
    """A FSolar plant (installation site).

    The ``id`` is the ``plantId`` used by the energy-flow endpoints and by the
    plant-scoped WebSocket.
    """

    id: str
    name: str
    address: str | None = None
    country_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    capacity_kw: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Plant:
        """Build a plant from the ``/plant/list_plant`` record."""
        from .._coerce import to_float  # local import to avoid a cycle at module load

        return cls(
            id=to_str(payload.get("id")) or "",
            name=to_str(payload.get("plantName")) or to_str(payload.get("name")) or "",
            address=to_str(payload.get("address")),
            country_id=to_str(payload.get("countryId")),
            latitude=to_float(payload.get("latitude")),
            longitude=to_float(payload.get("longitude")),
            capacity_kw=to_float(payload.get("ratedPower")),
            raw=dict(payload),
        )


@dataclass(frozen=True, slots=True)
class Device:
    """A physical device registered under a plant."""

    serial_number: str
    product_type: ProductType
    model: str | None = None
    device_type: str | None = None
    plant_id: str | None = None
    plant_name: str | None = None
    status: str | None = None
    firmware_version: str | None = None
    alias: str | None = None
    type_code: int | None = None
    sub_type: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Device:
        """Build a device from a ``/device/list_device*`` record."""
        return cls(
            serial_number=to_str(payload.get("deviceSn")) or "",
            product_type=ProductType.parse(payload.get("productTypeEnum")),
            model=to_str(payload.get("deviceModel")),
            device_type=to_str(payload.get("deviceType")),
            plant_id=to_str(payload.get("plantId")),
            plant_name=to_str(payload.get("plantName")),
            status=to_str(payload.get("status")),
            firmware_version=to_str(payload.get("firmwareVersion")),
            alias=to_str(payload.get("alias")) or to_str(payload.get("deviceAlias")),
            type_code=to_int(payload.get("typeCode")),
            sub_type=to_int(payload.get("subType")),
            raw=dict(payload),
        )

    @property
    def is_online(self) -> bool | None:
        """Whether the backend reports the device as online.

        Returns ``None`` when the status is unknown or in an unrecognised
        format, so that callers do not report a false negative.
        """
        if self.status is None:
            return None
        lowered = self.status.lower()
        if lowered in {"online", "1", "true", "connected"}:
            return True
        if lowered in {"offline", "0", "false", "disconnected"}:
            return False
        return None
