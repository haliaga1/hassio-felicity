"""Exceptions raised by the Felicity Solar client."""

from __future__ import annotations

__all__ = [
    "FelicityAPIError",
    "FelicityAuthError",
    "FelicityConnectionError",
    "FelicityError",
    "FelicityNotFoundError",
    "FelicityTokenExpiredError",
]


class FelicityError(Exception):
    """Base class for every error raised by this library."""


class FelicityConnectionError(FelicityError):
    """The FSolar API could not be reached (network, DNS, TLS, timeout)."""


class FelicityAuthError(FelicityError):
    """The supplied credentials were rejected by the FSolar API."""


class FelicityTokenExpiredError(FelicityAuthError):
    """The bearer token is no longer valid and must be refreshed.

    The FSolar gateway signals this with a ``302`` redirect to
    ``/token_expiration`` rather than with a ``401``.
    """


class FelicityAPIError(FelicityError):
    """The API answered with a non-success ``code``.

    Args:
        code: The business error code returned by the backend.
        message: The backend's i18n key for the error.
        path: The endpoint that produced the error, for diagnostics.
    """

    def __init__(self, code: int, message: str, path: str | None = None) -> None:
        self.code = code
        self.message = message
        self.path = path
        detail = f"[{code}] {message}"
        if path:
            detail = f"{detail} ({path})"
        super().__init__(detail)


class FelicityNotFoundError(FelicityError):
    """The requested plant, device or record does not exist."""
