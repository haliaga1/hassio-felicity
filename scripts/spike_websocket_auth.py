#!/usr/bin/env python3
"""Spike: does the FSolar WebSocket accept a bearer token without a cookie?

Closes the open question Q1 documented in ``docs/spikes/websocket-auth.md``.

Usage::

    FELICITY_TEST_EMAIL=... FELICITY_TEST_PASSWORD=... \\
        uv run python scripts/spike_websocket_auth.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from felicity_client import FelicityClient
from felicity_client.realtime import SubscriptionCommand, parse_snapshot_frame

TIMEOUT = 12.0


async def _try(client: FelicityClient, device_sn: str, *, with_token: bool) -> tuple[bool, str]:
    """Try one handshake variant and report whether a snapshot arrived."""
    import aiohttp

    url = f"{client.realtime._ws_base_url}/energy-flow/{device_sn}"
    headers: dict[str, str] = {}
    if with_token:
        token = await client.auth.get_token()
        headers["Authorization"] = token

    command = SubscriptionCommand(device_sn=device_sn)
    payload = command.to_payload()

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.ws_connect(url, headers=headers) as socket,
        ):
            await socket.send_str(json.dumps(payload))
            deadline = asyncio.get_running_loop().time() + TIMEOUT
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                message = await asyncio.wait_for(socket.receive(), timeout=remaining)
                if message.type is not aiohttp.WSMsgType.TEXT:
                    continue
                snapshot = parse_snapshot_frame(message.data)
                if snapshot is not None:
                    return True, f"received a snapshot for {snapshot.device_sn}"
    except TimeoutError:
        return False, "the handshake worked but no snapshot arrived in time"
    except Exception as exc:  # noqa: BLE001 - the point is to report the error
        return False, f"{type(exc).__name__}: {exc}"
    return False, "the socket closed without a snapshot"


async def main() -> int:
    """Run the spike."""
    email = os.environ.get("FELICITY_TEST_EMAIL")
    password = os.environ.get("FELICITY_TEST_PASSWORD")
    if not email or not password:
        print("FELICITY_TEST_EMAIL and FELICITY_TEST_PASSWORD are required")
        return 2

    async with FelicityClient(email, password) as client:
        devices = await client.list_devices()
        if not devices:
            print("The account has no device")
            return 1
        device = devices[0]
        print(f"Device: {device.serial_number} ({device.model})")

        with_token, message = await _try(client, device.serial_number, with_token=True)
        print(f"with Authorization   -> {'OK' if with_token else 'FAILED'}: {message}")

        without_token, message = await _try(client, device.serial_number, with_token=False)
        print(f"without any header   -> {'OK' if without_token else 'FAILED'}: {message}")

        if with_token and not without_token:
            print("\nVERDICT: the WebSocket needs the Authorization header.")
            print("The realtime transport can be the primary path.")
            return 0
        if with_token:
            print("\nVERDICT: the WebSocket works with or without the token.")
            return 0
        print("\nVERDICT: the WebSocket did not work. Keep REST polling as primary.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
