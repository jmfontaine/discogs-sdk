"""Experimental helpers, built on Discogs API behaviour that is not documented.

Each helper here documents the undocumented behaviour it depends on and what
follows when Discogs changes it, raises when it detects that the behaviour no
longer holds, and may change or be removed without a deprecation period. See
the design principles:
https://github.com/jmfontaine/discogs-sdk/blob/main/README.md#design-principles

Like ``discogs_sdk.oauth``, the module holds both variants: the plain name takes
a ``Discogs`` client and the ``async_`` one an ``AsyncDiscogs`` client.
"""

from discogs_sdk._async._experimental import (
    releases_added_since as async_releases_added_since,
)
from discogs_sdk._experimental_types import ReleasesAddedSince
from discogs_sdk._sync._experimental import releases_added_since

__all__ = [
    "ReleasesAddedSince",
    "async_releases_added_since",
    "releases_added_since",
]
