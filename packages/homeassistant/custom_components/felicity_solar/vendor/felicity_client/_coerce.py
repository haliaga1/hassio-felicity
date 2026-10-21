"""Normalisation helpers for the loosely-typed payloads returned by FSolar.

The backend returns every numeric value as a JSON string, and any field may be
``null`` or absent. The critical rule of this module is that **a missing value
is ``None``, never ``0.0``**: a fabricated zero is indistinguishable from a
stopped inverter and silently corrupts the Home Assistant statistics.

Every function is total — it never raises on bad input.
"""

from __future__ import annotations

from typing import Any, Final

__all__ = [
    "MISSING_TOKENS",
    "to_bool",
    "to_float",
    "to_int",
    "to_optional_float",
    "to_str",
]

#: Strings the backend uses to signal "no value".
MISSING_TOKENS: Final[frozenset[str]] = frozenset(
    {"", "-", "--", "null", "none", "nan", "n/a", "na"}
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in MISSING_TOKENS
    return False


def to_optional_float(value: Any) -> float | None:
    """Coerce a value to ``float``, returning ``None`` when it is missing.

    Booleans are rejected on purpose: ``True`` is not a measurement.
    """
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def to_float(value: Any, default: float | None = None) -> float | None:
    """Coerce to ``float``, falling back to ``default`` when missing.

    ``default`` defaults to ``None`` so that callers must opt in to fabricating
    a value.
    """
    coerced = to_optional_float(value)
    return default if coerced is None else coerced


def to_int(value: Any, default: int | None = None) -> int | None:
    """Coerce to ``int``, falling back to ``default`` when missing."""
    coerced = to_optional_float(value)
    if coerced is None:
        return default
    try:
        return int(coerced)
    except (ValueError, OverflowError):
        return default


def to_str(value: Any, default: str | None = None) -> str | None:
    """Coerce to ``str``, returning ``None`` for missing values."""
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in MISSING_TOKENS:
            return default
        return stripped
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return str(value)
    return default


def to_bool(value: Any, default: bool | None = None) -> bool | None:
    """Coerce to ``bool``.

    The backend sends booleans as real JSON booleans, as ``0``/``1`` integers
    and as the strings ``"true"``/``"false"`` depending on the endpoint.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default
