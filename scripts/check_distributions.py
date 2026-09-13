#!/usr/bin/env python
"""Validate the contents of built distributions before they are published.

Usage: ``python scripts/check_distributions.py dist``

The wheel and the sdist are held to different contracts. The wheel is what gets
imported, so it must carry the runtime package and nothing else; the sdist is
what a wheel gets rebuilt from, so it must carry the sources and packaging
metadata, and test files legitimately belong in it.

These are checks the test suite cannot make: a wheel missing ``py.typed`` or
shipping a stray ``tests/`` directory behaves identically at runtime.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

WHEEL_REQUIRED = (
    "discogs_sdk/__init__.py",
    "discogs_sdk/py.typed",
    "discogs_sdk/_async/_client.py",
    "discogs_sdk/_sync/_client.py",
    "discogs_sdk/models/__init__.py",
)
# Project-only trees: useful in the repository and in the sdist, wrong in the
# importable distribution.
WHEEL_FORBIDDEN_ROOTS = ("tests", "scripts", "examples", "docs")

SDIST_REQUIRED = (
    "pyproject.toml",
    "PKG-INFO",
    "LICENSE.txt",
    "README.md",
    "src/discogs_sdk/__init__.py",
    "src/discogs_sdk/py.typed",
    "src/discogs_sdk/_async/_client.py",
    "src/discogs_sdk/_sync/_client.py",
)


def fail(message: str) -> None:
    print(f"check_distributions: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()

    missing = [name for name in WHEEL_REQUIRED if name not in names]
    if missing:
        fail(f"{path.name} is missing {', '.join(missing)}")

    dist_info = {name for name in names if name.endswith(("dist-info/METADATA", "dist-info/RECORD"))}
    if len(dist_info) != 2:
        fail(f"{path.name} is missing dist-info METADATA or RECORD")

    leaked = sorted({name for name in names if name.split("/", 1)[0] in WHEEL_FORBIDDEN_ROOTS})
    if leaked:
        fail(f"{path.name} ships project-only paths: {', '.join(leaked)}")

    print(f"ok: {path.name} ({len(names)} entries)")


def check_sdist(path: Path) -> None:
    with tarfile.open(path) as archive:
        # Every member is under a single `<name>-<version>/` prefix.
        names = {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}

    missing = [name for name in SDIST_REQUIRED if name not in names]
    if missing:
        fail(f"{path.name} is missing {', '.join(missing)}")

    print(f"ok: {path.name} ({len(names)} entries)")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: check_distributions.py <dist-directory>")

    dist = Path(sys.argv[1])
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))

    if len(wheels) != 1 or len(sdists) != 1:
        fail(f"expected exactly one wheel and one sdist in {dist}, found {len(wheels)} and {len(sdists)}")

    check_wheel(wheels[0])
    check_sdist(sdists[0])


if __name__ == "__main__":
    main()
