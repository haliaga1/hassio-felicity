#!/usr/bin/env python3
"""Vendor the client library inside the Home Assistant integration.

Home Assistant installs a custom integration by copying its folder. A
dependency that lives on PyPI would have to be declared in the manifest,
and that means a pip install at setup time. Vendoring the client inside
the integration removes that step entirely: everything the integration
needs arrives with it.

The vendored copy is **generated**, never edited by hand. Run::

    uv run python scripts/sync_vendor.py

after changing the library.
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/felicity-client/src/felicity_client"
TARGET = ROOT / "custom_components/felicity_solar/vendor/felicity_client"

#: Files that must not be vendored.
EXCLUDED = {"__pycache__", "py.typed.orig"}


def _should_copy(path: Path) -> bool:
    """Whether a file belongs to the vendored copy."""
    if path.name in EXCLUDED:
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return "__pycache__" not in path.parts


def main() -> int:
    """Copy the library into the integration and report what changed."""
    if not SOURCE.is_dir():
        print(f"the source library is missing: {SOURCE}", file=sys.stderr)
        return 1

    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True, exist_ok=True)

    copied = 0
    for path in sorted(SOURCE.rglob("*.py")):
        if not _should_copy(path):
            continue
        relative = path.relative_to(SOURCE)
        destination = TARGET / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied += 1

    print(f"vendored {copied} module(s) into {TARGET.relative_to(ROOT)}")

    # The integration must import the vendored copy, never the installed one.
    integration = ROOT / "custom_components/felicity_solar"
    import re

    absolute_import = re.compile(r"^\s*(from|import)\s+felicity_client\b", re.MULTILINE)
    for path in integration.rglob("*.py"):
        if "vendor" in path.relative_to(integration).parts:
            continue
        text = path.read_text(encoding="utf-8")
        if absolute_import.search(text):
            print(
                f"ERROR: {path.relative_to(ROOT)} still imports the installed "
                "felicity_client; it must import the vendored one",
                file=sys.stderr,
            )
            return 1

    print("the integration imports the vendored copy only")
    return 0


def diff() -> bool:
    """Whether the vendored copy is up to date."""
    if not TARGET.is_dir():
        return False
    return all(
        filecmp.cmp(SOURCE / path.relative_to(TARGET), path, shallow=False)
        for path in TARGET.rglob("*.py")
    )


if __name__ == "__main__":
    sys.exit(main())
