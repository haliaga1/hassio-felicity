"""Authentication against the FSolar cloud.

Responsibilities:

* encrypt the password with the RSA public key the web app uses;
* exchange it for a bearer token via ``POST /userlogin``;
* decode the token's ``exp`` claim to know when to refresh;
* persist the token through a pluggable :class:`TokenStore` so that a restart
  does not force a new login.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._coerce import to_int
from .const import DEFAULT_LANG
from .crypto import (
    DEFAULT_PUBLIC_KEY_B64,
    PublicKeyExtractionError,
    encrypt_password,
    extract_public_key_b64,
    public_key_fingerprint,
)
from .exceptions import FelicityAPIError, FelicityAuthError

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "AuthService",
    "FileTokenStore",
    "NullTokenStore",
    "StoredToken",
    "TokenStore",
]

#: RSA error codes the backend returns when the ciphertext is not acceptable.
_RSA_ERROR_CODES = frozenset({10010027})


@dataclass(frozen=True, slots=True)
class StoredToken:
    """A bearer token together with its expiry."""

    token: str
    expires_at: float

    @property
    def is_expired(self) -> bool:
        """Whether the token is expired, with a 60 s safety margin."""
        return time.time() >= (self.expires_at - 60)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for storage."""
        return {"token": self.token, "expires_at": self.expires_at}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StoredToken | None:
        """Rebuild from storage, or ``None`` when the payload is unusable."""
        token = payload.get("token")
        expires_at = to_int(payload.get("expires_at"))
        if not isinstance(token, str) or not token or expires_at is None:
            return None
        return cls(token=token, expires_at=float(expires_at))


class TokenStore(ABC):
    """Where a bearer token is kept between runs."""

    @abstractmethod
    async def load(self, email: str) -> StoredToken | None:
        """Return the stored token for ``email``, if any."""

    @abstractmethod
    async def save(self, email: str, token: StoredToken) -> None:
        """Persist a token for ``email``."""

    @abstractmethod
    async def clear(self, email: str) -> None:
        """Forget the token stored for ``email``."""


class NullTokenStore(TokenStore):
    """A store that keeps nothing. Useful for tests and one-shot scripts."""

    async def load(self, email: str) -> StoredToken | None:
        """Always ``None``."""
        return None

    async def save(self, email: str, token: StoredToken) -> None:
        """No-op."""

    async def clear(self, email: str) -> None:
        """No-op."""


class FileTokenStore(TokenStore):
    """Stores tokens in a JSON file with ``0600`` permissions.

    The file holds one entry per account. It is intentionally *not* encrypted:
    Home Assistant should use its own encrypted store instead. This
    implementation is meant for scripts and for the library's standalone use.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        """The backing file path."""
        return self._path

    async def load(self, email: str) -> StoredToken | None:
        """Return the stored token for ``email``."""
        payload = self._read()
        entry = payload.get(email)
        if not isinstance(entry, dict):
            return None
        return StoredToken.from_dict(entry)

    async def save(self, email: str, token: StoredToken) -> None:
        """Persist a token for ``email``."""
        payload = self._read()
        payload[email] = token.to_dict()
        self._write(payload)

    async def clear(self, email: str) -> None:
        """Remove the token stored for ``email``."""
        payload = self._read()
        if payload.pop(email, None) is not None:
            self._write(payload)

    def _read(self) -> dict[str, Any]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return {}
        except OSError as exc:  # pragma: no cover - depends on the filesystem
            _LOGGER.warning("Could not read the token store %s: %s", self._path, exc)
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            _LOGGER.warning("Token store %s is not valid JSON, ignoring it", self._path)
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(self._path)


class AuthService:
    """Manages the FSolar session for one account."""

    def __init__(
        self,
        email: str,
        password: str,
        *,
        store: TokenStore | None = None,
        public_key_b64: str = DEFAULT_PUBLIC_KEY_B64,
        lang: str = DEFAULT_LANG,
    ) -> None:
        self._email = email
        self._password = password
        self._store: TokenStore = store or NullTokenStore()
        self._public_key_b64 = public_key_b64
        self._lang = lang
        self._token: StoredToken | None = None
        self._login_count = 0

    @property
    def email(self) -> str:
        """The account this service authenticates."""
        return self._email

    @property
    def public_key_fingerprint(self) -> str:
        """SHA-256 fingerprint of the RSA public key currently in use."""
        return public_key_fingerprint(self._public_key_b64)

    @property
    def login_count(self) -> int:
        """How many times a login has been performed. Useful in tests."""
        return self._login_count

    async def get_token(self) -> str:
        """Return a valid bearer token, refreshing it if needed."""
        if self._token is not None and not self._token.is_expired:
            return self._token.token

        stored = await self._store.load(self._email)
        if stored is not None and not stored.is_expired:
            self._token = stored
            _LOGGER.debug("Reusing the stored FSolar token for %s", self._email)
            return stored.token

        await self.login()
        assert self._token is not None  # noqa: S101 - login() always sets it
        return self._token.token

    async def login(self) -> StoredToken:
        """Authenticate and store the resulting token.

        If the backend rejects the RSA ciphertext, the public key is
        re-extracted from the live web app and the login is retried once.
        """
        payload = await self._login_request(self._public_key_b64)
        if payload is None:
            refreshed = await self._refresh_public_key()
            if refreshed is None:
                raise FelicityAuthError(
                    "the FSolar API rejected the encrypted password and the public "
                    "key could not be re-extracted from the web app"
                )
            _LOGGER.warning(
                "The embedded FSolar public key was rejected; re-extracted a new one (%s)",
                public_key_fingerprint(refreshed),
            )
            self._public_key_b64 = refreshed
            payload = await self._login_request(refreshed)

        assert payload is not None  # noqa: S101 - _login_request raises otherwise
        token = self._build_token(payload)
        self._token = token
        self._login_count += 1
        await self._store.save(self._email, token)
        _LOGGER.info(
            "Authenticated against FSolar as %s (token valid for %s)",
            self._email,
            _format_duration(token.expires_at - time.time()),
        )
        return token

    async def invalidate(self) -> None:
        """Drop the in-memory token so the next call triggers a fresh login."""
        self._token = None

    def restore(self, token: StoredToken) -> None:
        """Adopt a token that was obtained elsewhere.

        Used to resume a session from a persisted token without paying for a
        login round-trip.
        """
        self._token = token

    @property
    def current_token(self) -> StoredToken | None:
        """The token currently in use, if any."""
        return self._token

    async def logout(self) -> None:
        """Forget the token entirely."""
        self._token = None
        await self._store.clear(self._email)

    async def _login_request(self, public_key_b64: str) -> dict[str, Any] | None:
        """Perform one login attempt.

        Returns the raw payload on success, or ``None`` when the backend
        rejected the RSA ciphertext (which means the public key must be
        re-extracted before retrying).
        """
        from .http import FelicityHTTP  # local import avoids a circular dependency

        encrypted = encrypt_password(self._password, public_key_b64)
        payload: dict[str, Any] = {
            "userName": self._email,
            "password": encrypted,
            "version": "1.0",
        }
        http = FelicityHTTP(lang=self._lang)
        try:
            async with http:
                response = await http.post_raw("/userlogin", json=payload)
        except FelicityAPIError as exc:
            if exc.code in _RSA_ERROR_CODES:
                _LOGGER.debug("FSolar rejected the RSA ciphertext (code %s)", exc.code)
                return None
            raise

        if not isinstance(response, dict):
            raise FelicityAuthError("unexpected response shape from /userlogin")

        # The login endpoint is read raw, so the envelope is validated here.
        code = response.get("code")
        if code is not None and code != 200:
            message = str(response.get("message") or "login failed")
            if code in _RSA_ERROR_CODES:
                _LOGGER.debug("FSolar rejected the RSA ciphertext (code %s)", code)
                return None
            raise FelicityAuthError(f"the FSolar API rejected the login: [{code}] {message}")

        return response

    async def _refresh_public_key(self) -> str | None:
        """Fetch the login page and extract a fresh RSA public key from it."""
        from .http import FelicityHTTP  # local import avoids a circular dependency

        http = FelicityHTTP(lang=self._lang)
        try:
            async with http:
                key = await http.fetch_public_key()
        except (OSError, PublicKeyExtractionError) as exc:
            _LOGGER.warning("Could not re-extract the FSolar public key: %s", exc)
            return None
        return key

    def _build_token(self, payload: dict[str, Any]) -> StoredToken:
        """Turn a successful login payload into a :class:`StoredToken`."""
        data = payload.get("data")
        raw_token: object = None
        if isinstance(data, dict):
            raw_token = data.get("token")
        if not isinstance(raw_token, str) or not raw_token:
            raw_token = payload.get("token")
        if not isinstance(raw_token, str) or not raw_token:
            raise FelicityAuthError("the FSolar login response did not contain a token")

        expires_at = _decode_expiry(raw_token)
        if expires_at is None:
            # Without a usable expiry, assume a conservative 1 hour lifetime.
            _LOGGER.warning("Could not decode the FSolar token expiry, assuming 1 hour")
            expires_at = time.time() + 3600
        return StoredToken(token=raw_token, expires_at=expires_at)


def _decode_expiry(token: str) -> float | None:
    """Decode the ``exp`` claim of the FSolar JWT without verifying it.

    The backend does not publish a verification key, so the signature is not
    checked. This is acceptable here: the token is only used to talk to the
    same backend that issued it.
    """
    import base64
    import json

    payload = token.removeprefix("Bearer_")
    parts = payload.split(".")
    if len(parts) < 2:
        return None
    segment = parts[1]
    padding = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(segment + padding)
        claims = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    if not isinstance(exp, (int, float)):
        return None
    return float(exp)


def _format_duration(seconds: float) -> str:
    """Human readable duration, for log messages."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def extract_key_from_sources(sources: list[str]) -> str:
    """Module-level convenience wrapper around :func:`extract_public_key_b64`."""
    return extract_public_key_b64(*sources)
