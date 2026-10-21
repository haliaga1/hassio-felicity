"""Test helpers shared across the suite."""

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
