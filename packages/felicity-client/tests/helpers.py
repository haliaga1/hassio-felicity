"""Test helpers shared across the suite.

The fixtures are captured from the live FSolar API and redacted. They hold
the **unwrapped** ``data`` payload, because that is what the service layer
sees; :func:`envelope` puts them back into the ``{code, data, message}``
envelope the HTTP layer expects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by file name."""
    path = FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing fixture: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def envelope(data: Any, code: int = 200, message: str = "success") -> dict[str, Any]:
    """Wrap a payload in the FSolar response envelope."""
    return {"code": code, "data": data, "message": message}
