"""HTTP transport for the FSolar API.

Two behaviours of the FSolar gateway drive most of the design here:

1. A call without a valid token does **not** return ``401``. The gateway
   answers ``302 Found`` with ``Location: /token_expiration``. Redirects are
   therefore disabled and that specific response is translated into
   :class:`~felicity_client.exceptions.FelicityTokenExpiredError`.
2. Every response uses the ``{code, data, message}`` envelope. ``code != 200``
   means failure, and ``message`` is an i18n key rather than a human message.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urljoin

import httpx

from .const import (
    DEFAULT_LANG,
    DEFAULT_NODE,
    DEFAULT_TIMEOUT,
    INT_API_URL,
    INT_WS_URL,
    LOGIN_PAGE_URL,
    USER_AGENT,
)
from .crypto import PublicKeyExtractionError, collect_asset_urls, extract_public_key_b64
from .exceptions import (
    FelicityAPIError,
    FelicityConnectionError,
    FelicityNotFoundError,
    FelicityTokenExpiredError,
)

if TYPE_CHECKING:  # pragma: no cover
    from .auth import AuthService

_LOGGER = logging.getLogger(__name__)

__all__ = ["FelicityHTTP"]

#: The redirect target the gateway uses to signal an expired token.
_TOKEN_EXPIRATION_PATH = "/token_expiration"  # noqa: S105 - a path, not a credential

#: HTTP statuses that are worth retrying.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FelicityHTTP:
    """A thin, typed HTTP client for the FSolar REST API."""

    def __init__(
        self,
        *,
        base_url: str = INT_API_URL,
        node: str = DEFAULT_NODE,
        lang: str = DEFAULT_LANG,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        auth: AuthService | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._node = node
        self._lang = lang
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self._auth = auth
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            follow_redirects=False,
            headers={
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "lang": lang,
                "source": "WEB",
                "Node": node,
                "user-agent": USER_AGENT,
            },
        )

    @property
    def base_url(self) -> str:
        """The API base URL in use."""
        return self._base_url

    @property
    def ws_url(self) -> str:
        """The WebSocket base URL matching the REST base URL."""
        return (
            INT_WS_URL
            if self._base_url == INT_API_URL
            else self._base_url.replace("https://", "wss://").replace("http://", "ws://")
        )

    @property
    def client(self) -> httpx.AsyncClient:
        """The underlying ``httpx`` client."""
        return self._client

    def set_auth(self, auth: AuthService) -> None:
        """Attach the service used to obtain the bearer token."""
        self._auth = auth

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the client if this instance created it."""
        if self._owns_client:
            await self._client.aclose()

    async def post_raw(
        self,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """POST and return the raw JSON body, bypassing the envelope check."""
        return await self._request("POST", path, json=json, params=params, headers=headers)

    async def get_raw(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """GET and return the raw JSON body, bypassing the envelope check."""
        return await self._request("GET", path, params=params, headers=headers)

    async def post(
        self,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """POST and return the ``data`` member of the envelope."""
        payload = await self._request(
            "POST", path, json=json, params=params, headers=headers, authenticated=True
        )
        return _unwrap(payload, path)

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """GET and return the ``data`` member of the envelope."""
        payload = await self._request(
            "GET", path, params=params, headers=headers, authenticated=True
        )
        return _unwrap(payload, path)

    async def fetch_public_key(self) -> str:
        """Extract a live RSA public key from the FSolar web app.

        Used as a fallback when the embedded key is rejected by the backend.
        """
        page = await self._client.get(LOGIN_PAGE_URL)
        page.raise_for_status()
        sources = [page.text]

        for asset in collect_asset_urls(page.text)[:12]:
            url = urljoin(LOGIN_PAGE_URL, asset)
            try:
                response = await self._client.get(url)
            except httpx.HTTPError as exc:
                _LOGGER.debug("Could not fetch the asset %s: %s", url, exc)
                continue
            if response.status_code == 200:
                sources.append(response.text)

        try:
            return extract_public_key_b64(*sources)
        except PublicKeyExtractionError:
            # A second pass over the assets referenced *by* the bundles.
            deeper: list[str] = []
            for source in sources[1:]:
                for asset in collect_asset_urls(source)[:12]:
                    url = urljoin(LOGIN_PAGE_URL, asset)
                    try:
                        response = await self._client.get(url)
                    except httpx.HTTPError:
                        continue
                    if response.status_code == 200:
                        deeper.append(response.text)
            if not deeper:
                raise
            return extract_public_key_b64(*sources, *deeper)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        authenticated: bool = False,
        _retried_auth: bool = False,
    ) -> Any:
        """Perform one HTTP request with retries and error translation."""
        request_headers = dict(headers or {})
        if authenticated:
            request_headers["Authorization"] = await self._authorization_header()

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.request(
                    method, path, json=json, params=params, headers=request_headers
                )
            except httpx.TimeoutException as exc:
                last_error = FelicityConnectionError(f"the request to {path} timed out")
                _LOGGER.debug("Timeout on %s (attempt %s): %s", path, attempt, exc)
            except httpx.HTTPError as exc:
                last_error = FelicityConnectionError(f"could not reach the FSolar API: {exc}")
                _LOGGER.debug("Network error on %s (attempt %s): %s", path, attempt, exc)
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = FelicityAPIError(
                        response.status_code, f"HTTP {response.status_code}", path
                    )
                    _LOGGER.debug(
                        "Retryable status %s on %s (attempt %s)",
                        response.status_code,
                        path,
                        attempt,
                    )
                elif response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    if _TOKEN_EXPIRATION_PATH in location:
                        if _retried_auth:
                            raise FelicityTokenExpiredError(
                                "the FSolar token was rejected after a refresh attempt"
                            )
                        _LOGGER.info("The FSolar token expired, refreshing it")
                        if self._auth is not None:
                            await self._auth.invalidate()
                        return await self._request(
                            method,
                            path,
                            json=json,
                            params=params,
                            headers=headers,
                            authenticated=authenticated,
                            _retried_auth=True,
                        )
                    last_error = FelicityAPIError(
                        response.status_code, f"unexpected redirect to {location}", path
                    )
                elif response.status_code == 404:
                    raise FelicityNotFoundError(f"{path} returned HTTP 404")
                elif response.status_code >= 400:
                    raise FelicityAPIError(
                        response.status_code, f"HTTP {response.status_code}", path
                    )
                else:
                    return _parse_json(response, path)

            if attempt < self._max_retries:
                await _sleep_backoff(attempt)

        assert last_error is not None  # noqa: S101 - the loop always sets it
        raise last_error

    async def _authorization_header(self) -> str:
        """Return the ``Authorization`` header value for an authenticated call."""
        if self._auth is None:
            raise FelicityTokenExpiredError("no auth service is attached to this client")
        return await self._auth.get_token()


def _parse_json(response: httpx.Response, path: str) -> Any:
    """Decode a JSON body, with a helpful error for non-JSON responses."""
    try:
        return response.json()
    except ValueError as exc:
        body = response.text[:200]
        raise FelicityAPIError(
            response.status_code, f"invalid JSON response: {body}", path
        ) from exc


def _unwrap(payload: Any, path: str) -> Any:
    """Validate the ``{code, data, message}`` envelope and return ``data``."""
    if not isinstance(payload, Mapping):
        raise FelicityAPIError(0, f"unexpected response shape: {type(payload).__name__}", path)

    code = payload.get("code")
    if code is None:
        # Some endpoints answer with a bare payload.
        return payload

    if code != 200:
        message = payload.get("message") or payload.get("data") or "unknown error"
        raise FelicityAPIError(int(code), str(message), path)

    return payload.get("data")


async def _sleep_backoff(attempt: int, base: float = 0.5, cap: float = 8.0) -> None:
    """Sleep with exponential backoff and jitter."""
    delay = min(cap, base * (2.0 ** (attempt - 1)))
    jitter = random.uniform(0, delay * 0.25)  # noqa: S311 - jitter, not a secret
    await asyncio.sleep(delay + jitter)
