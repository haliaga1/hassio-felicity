"""Device-level operations: discovery and live snapshots."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime

from .._coerce import to_str
from ..http import FelicityHTTP
from ..models.common import Device
from ..models.snapshot import Snapshot
from .plants import extract_list

_LOGGER = logging.getLogger(__name__)

__all__ = ["DeviceService"]

#: The ``deviceType`` the reference web client sends. The backend appears to
#: accept it for every product family.
_DEFAULT_DEVICE_TYPE = "BP"

#: The timestamp format expected by ``get_device_snapshot``.
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class DeviceService:
    """Reads the devices of an account and their live telemetry."""

    def __init__(self, http: FelicityHTTP) -> None:
        self._http = http

    async def list_devices(
        self,
        *,
        plant_id: str | None = None,
        page_size: int = 50,
    ) -> list[Device]:
        """Return the devices of the account, optionally filtered by plant.

        The ``list_device_all_type`` endpoint is used because it returns every
        device regardless of its family in a single flat payload, which is
        exactly what the Home Assistant integration needs.
        """
        devices: list[Device] = []
        seen: set[str] = set()
        page = 1

        while True:
            data = await self._http.post(
                "/device/list_device_all_type",
                json={
                    "pageNum": page,
                    "pageSize": page_size,
                    "deviceSn": "",
                    "status": "",
                    "sampleFlag": "",
                    "oscFlag": "",
                },
            )
            rows, total = extract_list(data)
            if not rows:
                break

            for row in rows:
                device = Device.from_payload(row)
                if not device.serial_number or device.serial_number in seen:
                    continue
                if plant_id is not None and device.plant_id not in (None, plant_id):
                    # A device without a plant id is not attributable, so it
                    # is excluded rather than silently attached to the plant.
                    continue
                seen.add(device.serial_number)
                devices.append(device)

            _LOGGER.debug("Loaded %s device(s) on page %s", len(rows), page)
            if len(devices) >= total or len(rows) < page_size:
                break
            page += 1

        _LOGGER.info("Found %s device(s) for the account", len(devices))
        return devices

    async def get_device(self, device_sn: str) -> Device:
        """Return the metadata of a single device."""
        devices = await self.list_devices()
        for device in devices:
            if device.serial_number == device_sn:
                return device
        raise ValueError(f"device {device_sn} is not registered on this account")

    async def get_snapshot(
        self,
        device_sn: str,
        *,
        device_type: str = _DEFAULT_DEVICE_TYPE,
        date_str: str | None = None,
    ) -> Snapshot:
        """Return the live telemetry of a device."""
        payload = await self._http.post(
            "/device/get_device_snapshot",
            json={
                "deviceSn": device_sn,
                "deviceType": device_type,
                "dateStr": date_str or datetime.now().strftime(_DATE_FORMAT),
            },
        )
        if not isinstance(payload, Mapping):
            raise ValueError(f"unexpected snapshot payload for {device_sn}")

        if not to_str(payload.get("deviceSn")):
            # The backend answers 200 with an empty body when the device is
            # unknown or has never reported.
            raise ValueError(f"the FSolar API returned an empty snapshot for {device_sn}")

        return Snapshot.from_payload(payload)
