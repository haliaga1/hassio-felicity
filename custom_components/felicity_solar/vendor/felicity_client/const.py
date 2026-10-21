"""Constants shared across the Felicity Solar client."""

from __future__ import annotations

from typing import Final, Literal

__all__ = [
    "DEFAULT_LANG",
    "DEFAULT_NODE",
    "DEFAULT_TIMEOUT",
    "DEFAULT_WS_RECONNECT_MAX_DELAY",
    "DEFAULT_WS_RECONNECT_MIN_DELAY",
    "EU_API_URL",
    "EU_WS_URL",
    "INT_API_URL",
    "INT_WS_URL",
    "KEEPALIVE_INTERVAL",
    "LOGIN_PAGE_URL",
    "USER_AGENT",
    "WS_KEEPALIVE_SECONDS",
]

#: International (INT) API node. The European node mirrors the same contract.
INT_API_URL: Final = "https://shine-api.felicitysolar.com"
#: The WebSocket base URL carries a ``/socket`` prefix; without it the
#: handshake answers 404.
INT_WS_URL: Final = "wss://shine-api.felicitysolar.com/socket"

EU_API_URL: Final = "https://shine-api.felicitysolar.com"
EU_WS_URL: Final = "wss://shine-api.felicitysolar.com/socket"

DEFAULT_NODE: Final = "INT"
DEFAULT_LANG: Final = "en_US"

#: REST request timeout, in seconds.
DEFAULT_TIMEOUT: Final = 15.0

#: The public web app used to bootstrap the login flow and to extract the
#: RSA public key when the embedded one is rejected by the backend.
LOGIN_PAGE_URL: Final = "https://shine.felicitysolar.com/login"

USER_AGENT: Final = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

#: The web app re-sends the subscription command on this cadence as a
#: keepalive. Mirroring it keeps the socket alive on the server side.
WS_KEEPALIVE_SECONDS: Final = 10.0

#: Alias kept for readability at the call sites.
KEEPALIVE_INTERVAL: Final = WS_KEEPALIVE_SECONDS

#: Reconnect backoff bounds, in seconds.
DEFAULT_WS_RECONNECT_MIN_DELAY: Final = 1.0
DEFAULT_WS_RECONNECT_MAX_DELAY: Final = 60.0

ApiNode = Literal["INT", "EU"]
