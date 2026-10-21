"""Real-time telemetry over the FSolar WebSocket.

The FSolar web app does not poll for live data: it opens a WebSocket per
device (``/energy-flow/{deviceSn}``) or per plant
(``/energy-plant-flow/{plantId}``), sends a subscription command, and then
receives ``{"realTimeData": {"deviceSnapshot": {...}}}`` frames.

This module reproduces that protocol:

* the subscription command is sent immediately after the handshake **and**
  re-sent every 10 seconds, exactly like the web app, because the server
  drops sockets that go quiet;
* the connection is re-established with exponential backoff and jitter;
* the caller consumes snapshots through a plain async generator, so the
  Home Assistant integration can treat WebSocket and polling identically.

``aiohttp`` is used instead of ``websockets`` on purpose: Home Assistant
already ships ``aiohttp``, so the integration needs **no** extra pip
install at setup time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    DEFAULT_WS_RECONNECT_MAX_DELAY,
    DEFAULT_WS_RECONNECT_MIN_DELAY,
    WS_KEEPALIVE_SECONDS,
)
from .models.snapshot import Snapshot

_LOGGER = logging.getLogger(__name__)

__all__ = ["RealtimeService", "SubscriptionCommand", "parse_snapshot_frame"]

#: The frames the server sends that carry a device snapshot.
_SNAPSHOT_KEYS = ("realTimeData", "deviceSnapshot", "data")


@dataclass(frozen=True, slots=True)
class SubscriptionCommand:
    """The command the web app sends to subscribe to a device's telemetry."""

    device_sn: str
    collector_sn: str = ""

    def to_payload(self, *, plant: bool = False) -> dict[str, Any]:
        """Render the command as the JSON payload the server expects."""
        if plant:
            return {"type": "command", "plant": True}
        return {
            "type": "command",
            "plant": False,
            "deviceCommand": {
                "deviceSn": self.device_sn,
                "collectorSn": self.collector_sn,
            },
        }


def parse_snapshot_frame(raw: str | bytes) -> Snapshot | None:
    """Extract a :class:`Snapshot` from a WebSocket frame.

    Returns ``None`` for frames that do not carry a snapshot (keepalives,
    acknowledgements, errors).
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        _LOGGER.debug("Ignoring a non-JSON WebSocket frame")
        return None

    candidate = _unwrap_snapshot(payload)
    if candidate is None:
        return None

    return Snapshot.from_payload(candidate)


def _unwrap_snapshot(payload: Any) -> dict[str, Any] | None:
    """Descend through the envelope keys until a snapshot record is found.

    The server nests the payload differently depending on the channel:
    ``{"realTimeData": {"deviceSnapshot": {...}}}``, ``{"deviceSnapshot": {...}}``
    or the snapshot at the top level.
    """
    candidate = payload
    for _ in range(len(_SNAPSHOT_KEYS) + 1):
        if not isinstance(candidate, dict):
            return None
        if "productTypeEnum" in candidate or "deviceSn" in candidate:
            return candidate
        for key in _SNAPSHOT_KEYS:
            nested = candidate.get(key)
            if isinstance(nested, dict):
                candidate = nested
                break
        else:
            return None
    return None


class RealtimeService:
    """Streams live snapshots from the FSolar WebSocket."""

    def __init__(
        self,
        ws_base_url: str,
        *,
        token_provider: Callable[[], Awaitable[str]] | None = None,
        keepalive_seconds: float = WS_KEEPALIVE_SECONDS,
        reconnect_min_delay: float = DEFAULT_WS_RECONNECT_MIN_DELAY,
        reconnect_max_delay: float = DEFAULT_WS_RECONNECT_MAX_DELAY,
        max_reconnect_attempts: int = 10,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._ws_base_url = ws_base_url.rstrip("/")
        self._token_provider = token_provider
        self._keepalive = keepalive_seconds
        self._reconnect_min_delay = reconnect_min_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._session = session
        self._owns_session = session is None
        self._connected = False
        self._connection_count = 0

    @property
    def is_connected(self) -> bool:
        """Whether the socket is currently open."""
        return self._connected

    @property
    def connection_count(self) -> int:
        """How many times a socket has been opened. Useful in tests."""
        return self._connection_count

    async def stream_device(
        self, device_sn: str, collector_sn: str = ""
    ) -> AsyncIterator[Snapshot]:
        """Yield live snapshots for a single device, forever."""
        command = SubscriptionCommand(device_sn=device_sn, collector_sn=collector_sn)
        url = f"{self._ws_base_url}/energy-flow/{device_sn}"
        async for snapshot in self._stream(url, command):
            yield snapshot

    async def stream_plant(self, plant_id: str) -> AsyncIterator[Snapshot]:
        """Yield live snapshots for a whole plant."""
        command = SubscriptionCommand(device_sn=plant_id)
        url = f"{self._ws_base_url}/energy-plant-flow/{plant_id}"
        async for snapshot in self._stream(url, command, plant=True):
            yield snapshot

    async def _stream(
        self, url: str, command: SubscriptionCommand, *, plant: bool = False
    ) -> AsyncIterator[Snapshot]:
        """Open, subscribe to, and yield from a socket, reconnecting on failure."""
        attempt = 0

        while True:
            try:
                async for snapshot in self._session_run(url, command, plant=plant):
                    attempt = 0
                    yield snapshot
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                if attempt > self._max_reconnect_attempts:
                    _LOGGER.error(
                        "Giving up on the FSolar WebSocket %s after %s attempts: %s",
                        url,
                        attempt,
                        exc,
                    )
                    raise

                delay = self._backoff_delay(attempt)
                _LOGGER.warning(
                    "The FSolar WebSocket %s failed (%s), reconnecting in %.1fs",
                    url,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _session_run(
        self, url: str, command: SubscriptionCommand, *, plant: bool
    ) -> AsyncIterator[Snapshot]:
        """Run one socket session until it fails."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True

        headers = await self._handshake_headers()
        payload = command.to_payload(plant=plant)

        try:
            async with self._session.ws_connect(url, headers=headers) as socket:
                self._connected = True
                self._connection_count += 1
                _LOGGER.info("Connected to the FSolar WebSocket %s", url)

                try:
                    await socket.send_str(json.dumps(payload))
                    keepalive = asyncio.create_task(self._keepalive_loop(socket, payload))
                    try:
                        async for message in socket:
                            if message.type is not aiohttp.WSMsgType.TEXT:
                                continue
                            snapshot = parse_snapshot_frame(message.data)
                            if snapshot is not None:
                                yield snapshot
                    finally:
                        keepalive.cancel()
                        await asyncio.gather(keepalive, return_exceptions=True)
                finally:
                    self._connected = False
                    _LOGGER.info("Disconnected from the FSolar WebSocket %s", url)
        finally:
            if self._owns_session and self._session is not None:
                await self._session.close()
                self._session = None
                self._owns_session = False

    async def _handshake_headers(self) -> dict[str, str]:
        """Build the headers sent with the WebSocket handshake.

        The web app relies on the browser session cookie, which a server
        client does not have. Whether the ``Authorization`` header alone is
        accepted is tracked as open question Q1 in ``SPECS.md``; the spike
        ``docs/spikes/websocket-auth.md`` records the verdict.
        """
        if self._token_provider is None:
            return {}
        try:
            token = await self._token_provider()
        except Exception as exc:  # noqa: BLE001 - a token failure must not kill the socket
            _LOGGER.debug("Could not obtain a token for the WebSocket handshake: %s", exc)
            return {}
        if not token:
            return {}
        return {"Authorization": token}

    async def _keepalive_loop(self, socket: Any, payload: dict[str, Any]) -> None:
        """Re-send the subscription command periodically, like the web app."""
        while True:
            await asyncio.sleep(self._keepalive)
            try:
                await socket.send_str(json.dumps(payload))
            except Exception as exc:  # noqa: BLE001 - the session will handle the failure
                _LOGGER.debug("Could not send the WebSocket keepalive: %s", exc)
                return

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter, bounded by the configured maximum."""
        delay = min(
            self._reconnect_max_delay,
            self._reconnect_min_delay * (2.0 ** (attempt - 1)),
        )
        jitter = random.uniform(0, delay * 0.25)  # noqa: S311 - jitter, not a secret
        return delay + jitter
