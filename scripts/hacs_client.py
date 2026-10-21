#!/usr/bin/env python3
"""Talk to the HACS websocket API of a Home Assistant instance.

HACS has no REST API: everything goes through the Home Assistant websocket
with the ``hacs/*`` command namespace. This helper is what installs a
custom repository and its integration without touching the file system of
the Home Assistant host.

Usage::

    export HA_URL="http://192.168.1.5:8123"
    export HA_TOKEN="..."
    uv run python scripts/hacs_client.py <comando> [json]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import aiohttp


class HassWebsocket:
    """A minimal Home Assistant websocket client."""

    def __init__(self, url: str, token: str) -> None:
        self._url = url.replace("http://", "ws://").replace("https://", "wss://")
        self._url = f"{self._url}/api/websocket"
        self._token = token
        self._next_id = 1

    async def __aenter__(self) -> HassWebsocket:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self._url)
        await self._authenticate()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._ws.close()
        await self._session.close()

    async def _authenticate(self) -> None:
        message = await self._ws.receive_json()
        if message.get("type") != "auth_required":
            raise RuntimeError(f"unexpected handshake: {message}")
        await self._ws.send_json({"type": "auth", "access_token": self._token})
        result = await self._ws.receive_json()
        if result.get("type") != "auth_ok":
            raise RuntimeError(f"authentication failed: {result}")

    async def command(self, command_type: str, **payload: Any) -> Any:
        """Send a command and return its result."""
        message_id = self._next_id
        self._next_id += 1
        await self._ws.send_json({"id": message_id, "type": command_type, **payload})

        while True:
            message = await self._ws.receive_json()
            if message.get("id") != message_id:
                continue  # an event, not our answer
            if not message.get("success"):
                raise RuntimeError(
                    f"{command_type} failed: {message.get('error', {}).get('message')}"
                )
            return message.get("result")


async def main() -> int:
    """Run one HACS command."""
    url = os.environ.get("HA_URL", "http://192.168.1.5:8123")
    token = os.environ.get("HA_TOKEN")
    if not token:
        print("HA_TOKEN is required")
        return 2

    command = sys.argv[1] if len(sys.argv) > 1 else "hacs/info"
    extra: dict[str, Any] = {}
    if len(sys.argv) > 2:
        extra = json.loads(sys.argv[2])

    async with HassWebsocket(url, token) as hass:
        try:
            result = await hass.command(command, **extra)
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
