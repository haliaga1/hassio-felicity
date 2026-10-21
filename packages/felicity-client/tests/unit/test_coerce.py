"""Unit tests for the value coercion helpers."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from felicity_client._coerce import to_bool, to_float, to_int, to_optional_float, to_str


class TestToOptionalFloat:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("12.5", 12.5),
            ("-3.25", -3.25),
            ("0", 0.0),
            ("  7.5  ", 7.5),
            (12, 12.0),
            (12.5, 12.5),
            ("1e3", 1000.0),
        ],
    )
    def test_parses_valid_values(self, raw: object, expected: float) -> None:
        assert to_optional_float(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [None, "", "  ", "-", "--", "null", "None", "N/A", "abc", "12,5", True, False, [], {}],
    )
    def test_returns_none_for_missing_or_invalid(self, raw: object) -> None:
        assert to_optional_float(raw) is None

    def test_never_fabricates_a_zero(self) -> None:
        """A missing measurement must be None, never 0.0."""
        for raw in (None, "", "null"):
            value = to_optional_float(raw)
            assert value is None
            assert value != 0.0

    @given(st.floats(allow_nan=False, allow_infinity=False, width=32))
    def test_round_trips_floats(self, value: float) -> None:
        assert to_optional_float(value) == value

    @given(st.integers(min_value=-(10**9), max_value=10**9))
    def test_round_trips_integers(self, value: int) -> None:
        assert to_optional_float(value) == float(value)


class TestToFloat:
    def test_uses_the_default_only_when_missing(self) -> None:
        assert to_float("4.2") == 4.2
        assert to_float(None) is None
        assert to_float(None, 0.0) == 0.0
        assert to_float("bad", 0.0) == 0.0


class TestToInt:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("42", 42), ("42.9", 42), ("-7", -7), (7, 7), (7.2, 7)],
    )
    def test_parses_valid_values(self, raw: object, expected: int) -> None:
        assert to_int(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "abc", True, False])
    def test_returns_none_for_missing_values(self, raw: object) -> None:
        assert to_int(raw) is None

    def test_handles_infinity(self) -> None:
        assert to_int("inf") is None
        assert to_int("-inf") is None
        assert not math.isnan(to_int("nan") or 0.0)


class TestToStr:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("abc", "abc"), ("  abc  ", "abc"), (42, "42"), (4.5, "4.5")],
    )
    def test_parses_valid_values(self, raw: object, expected: str) -> None:
        assert to_str(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "  ", "-", "null", True, False, [], {}])
    def test_returns_none_for_missing_values(self, raw: object) -> None:
        assert to_str(raw) is None


class TestToBool:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
            ("true", True),
            ("FALSE", False),
            ("Yes", True),
            ("off", False),
        ],
    )
    def test_parses_valid_values(self, raw: object, expected: bool) -> None:
        assert to_bool(raw) is expected

    @pytest.mark.parametrize("raw", [None, "maybe", [], {}])
    def test_returns_none_for_unknown_values(self, raw: object) -> None:
        assert to_bool(raw) is None
