"""The high-level Felicity Solar client.

Typical use::

    from felicity_client import FelicityClient

    async with FelicityClient(email, password) as client:
        plants = await client.list_plants()
        devices = await client.list_devices(plant_id=plants[0].id)
        snapshot = await client.get_snapshot(devices[0].serial_number)
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any, Self

from .auth import AuthService, TokenStore
from .const import DEFAULT_LANG, DEFAULT_NODE, DEFAULT_TIMEOUT, INT_API_URL, INT_WS_URL
from .http import FelicityHTTP
from .models.alerts import Alert, AlertGroup
from .models.common import Device, Plant
from .models.energy import EnergyFlow
from .models.snapshot import Snapshot
from .realtime import RealtimeService
from .services.alerts import AlertService
from .services.devices import DeviceService
from .services.energy import EnergyService
from .services.plants import PlantService

_LOGGER = logging.getLogger(__name__)

__all__ = ["FelicityClient"]


class FelicityClient:
    """An async client for the Felicity Solar (FSolar) cloud API.

    Args:
        email: The account used to sign in to the FSolar web app.
        password: The account password. It is encrypted with RSA before
            being sent, and never stored in clear text.
        token_store: Where to persist the bearer token between runs.
        base_url: The API base URL. Defaults to the international node.
        ws_url: The WebSocket base URL. Defaults to the international node.
        node: The backend node identifier sent in the ``Node`` header.
        lang: The language sent in the ``lang`` header.
        timeout: Per-request timeout, in seconds.
    """

    def __init__(
        self,
        email: str,
        password: str,
        *,
        token_store: TokenStore | None = None,
        base_url: str = INT_API_URL,
        ws_url: str = INT_WS_URL,
        node: str = DEFAULT_NODE,
        lang: str = DEFAULT_LANG,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._auth = AuthService(
            email,
            password,
            store=token_store,
            lang=lang,
        )
        self._http = FelicityHTTP(
            base_url=base_url,
            node=node,
            lang=lang,
            timeout=timeout,
            auth=self._auth,
        )
        self._realtime = RealtimeService(
            ws_url,
            token_provider=self._auth.get_token,
        )
        self._plants = PlantService(self._http)
        self._devices = DeviceService(self._http)
        self._energy = EnergyService(self._http)
        self._alerts = AlertService(self._http)

    @property
    def auth(self) -> AuthService:
        """The authentication service."""
        return self._auth

    @property
    def http(self) -> FelicityHTTP:
        """The HTTP transport."""
        return self._http

    @property
    def realtime(self) -> RealtimeService:
        """The WebSocket service."""
        return self._realtime

    async def __aenter__(self) -> Self:
        """Authenticate and enter the async context manager."""
        await self._auth.get_token()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying HTTP client."""
        await self._http.__aexit__(exc_type, exc, tb)

    async def list_plants(self) -> list[Plant]:
        """Return the plants attached to the account."""
        return await self._plants.list_plants()

    async def get_plant(self, plant_id: str) -> Plant:
        """Return the details of one plant."""
        return await self._plants.get_plant(plant_id)

    async def list_devices(self, *, plant_id: str | None = None) -> list[Device]:
        """Return the devices of the account, optionally filtered by plant."""
        return await self._devices.list_devices(plant_id=plant_id)

    async def get_device(self, device_sn: str) -> Device:
        """Return the metadata of one device."""
        return await self._devices.get_device(device_sn)

    async def get_snapshot(self, device_sn: str, **kwargs: Any) -> Snapshot:
        """Return the live telemetry of one device."""
        return await self._devices.get_snapshot(device_sn, **kwargs)

    async def get_snapshots(self, device_sns: list[str]) -> dict[str, Snapshot]:
        """Return the live telemetry of several devices.

        A device that fails does not abort the others: its entry is simply
        absent from the result.
        """
        results: dict[str, Snapshot] = {}
        for device_sn in device_sns:
            try:
                results[device_sn] = await self.get_snapshot(device_sn)
            except Exception as exc:  # noqa: BLE001 - one bad device must not stop the rest
                _LOGGER.warning("Could not read the snapshot of %s: %s", device_sn, exc)
        return results

    async def get_energy_flow(self, device_sn: str, plant_id: str) -> EnergyFlow:
        """Return the instantaneous energy flow of a device within a plant."""
        return await self._energy.get_energy_flow(device_sn, plant_id)

    async def list_alerts(self, device_sn: str | None = None) -> list[Alert]:
        """Return the active warnings of the account."""
        return await self._alerts.list_alerts(device_sn)

    async def list_alert_groups(self, device_sn: str | None = None) -> list[AlertGroup]:
        """Return the active warnings grouped by device."""
        return await self._alerts.list_alert_groups(device_sn)

    async def acknowledge_alert(self, alert_id: str, status: int = 1) -> bool:
        """Mark an alert as seen."""
        return await self._alerts.acknowledge(alert_id, status)
