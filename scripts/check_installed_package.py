#!/usr/bin/env python
"""Smoke-check an installed discogs-sdk wheel.

Run with the interpreter of an environment where the wheel was installed from
its published metadata (not from ``uv.lock``). It asserts the dependency floors
that metadata is supposed to enforce, then exercises the parts of the SDK that
need no network: model validation and lazy proxy construction.

The pydantic floor is the interesting part. Python 3.15 needs pydantic 2.14 or
newer, whose pydantic-core pin ships cp315 wheels, and environment markers are
easy to write in a way that silently skips that floor on a prerelease
interpreter, leaving the install with an unbuildable pydantic-core.
"""

from __future__ import annotations

import sys

import pydantic

from discogs_sdk import Discogs
from discogs_sdk.models import Release

MINIMUM_PYDANTIC = (2, 12)
# KLUDGE: mirrors the temporary Python 3.15 clause in pyproject.toml — 2.13 and
# earlier have no cp315 wheels, and the upper bound keeps the prerelease
# selection that the beta floor enables from reaching a later pydantic series.
# When that clause becomes `pydantic>=2.14; python_version=='3.15'`, drop only
# the upper bound here: the 3.15 branch must keep asserting the 2.14 minimum.
PYDANTIC_RANGE_315 = ((2, 14), (2, 15))


def installed_pydantic() -> tuple[int, int]:
    major, minor = pydantic.VERSION.split(".")[:2]
    return int(major), int(minor)


def main() -> None:
    installed = installed_pydantic()
    if sys.version_info[:2] == (3, 15):
        low, high = PYDANTIC_RANGE_315
        if not low <= installed < high:
            raise SystemExit(
                f"pydantic {pydantic.VERSION} is outside the {'.'.join(map(str, low))}–"
                f"{'.'.join(map(str, high))} range required on Python {sys.version.split()[0]}"
            )
    elif installed < MINIMUM_PYDANTIC:
        raise SystemExit(
            f"pydantic {pydantic.VERSION} is below the {'.'.join(map(str, MINIMUM_PYDANTIC))} floor required on "
            f"Python {sys.version.split()[0]}"
        )

    release = Release.model_validate(
        {
            "id": 352665,
            "title": "The Downward Spiral",
            "year": 1994,
            "labels": [{"id": 647, "name": "Nothing Records", "catno": "IND 92346"}],
        }
    )
    labels = release.labels or []
    assert [label.catalog_number for label in labels] == ["IND 92346"], labels

    with Discogs(token="not-a-real-token") as client:
        # Lazy proxies must not perform any HTTP call on construction.
        proxy = client.releases.get(352665)
        assert "352665" in repr(proxy), repr(proxy)

    print(f"ok: python {sys.version.split()[0]}, pydantic {pydantic.VERSION}")


if __name__ == "__main__":
    main()
