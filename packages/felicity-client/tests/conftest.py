"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import respx
from helpers import load_fixture


@pytest.fixture
def fixtures() -> Any:
    """Expose the fixture loader to the tests."""
    return load_fixture


@pytest.fixture(autouse=True)
def _mock_api() -> Iterator[respx.MockRouter]:
    """Intercept every HTTP call so no test ever touches the network.

    ``respx.mock`` is the *global* router; the routes registered with
    ``respx.get(...)`` / ``respx.post(...)`` land on it, so it has to be the
    one that gets activated here.
    """
    with respx.mock:
        yield respx.mock
