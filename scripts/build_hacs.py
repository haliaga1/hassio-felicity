#!/usr/bin/env python3
"""Build the HACS-ready tree from the monorepo.

Home Assistant installs a custom integration by copying its folder, so the
repository that HACS reads must have this layout at its root::

    custom_components/felicity_solar/     the integration (with the vendored client)
    hacs.json
    README.md
    LICENSE

This script assembles that tree in ``dist/hacs`` so it can be pushed to
``haliaga1/hassio-felicity`` or attached to a HACS release.

Usage::

    uv run python scripts/build_hacs.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/homeassistant"
DIST = ROOT / "dist/hacs"

#: What ends up in the published tree.
INCLUDE = ("custom_components", "hacs.json", "README.md", "LICENSE")


def main() -> int:
    """Assemble the HACS tree."""
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    for name in INCLUDE:
        source = ROOT / name if name in {"LICENSE"} else SOURCE / name
        if not source.exists():
            source = ROOT / name
        if not source.exists():
            print(f"missing: {source}", file=sys.stderr)
            return 1
        destination = DIST / name
        if source.is_dir():
            shutil.copytree(
                source,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )
        else:
            shutil.copy2(source, destination)

    # The integration must not carry the requirements of the standalone
    # library: everything it needs is vendored.
    manifest_path = DIST / "custom_components/felicity_solar/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["requirements"] = []
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    files = sorted(p for p in DIST.rglob("*") if p.is_file())
    print(f"built {DIST.relative_to(ROOT)} with {len(files)} file(s):")
    for path in files:
        if "vendor" not in path.parts:
            print(f"  {path.relative_to(DIST)}")
    print(f"  (+ {sum(1 for p in files if 'vendor' in p.parts)} vendored module(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
