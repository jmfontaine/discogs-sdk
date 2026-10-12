"""PageResult, the snapshot fetch() returns, is a plain immutable value."""

from __future__ import annotations

import copy
import dataclasses
import pickle

import pytest

from discogs_sdk import PageResult
from discogs_sdk.models.artist import ArtistRelease
from tests.conftest import make_artist_release


def _result() -> PageResult[ArtistRelease]:
    return PageResult(
        items=[ArtistRelease.model_validate(make_artist_release(id=2))],
        page=2,
        per_page=1,
        total_items=3,
        total_pages=3,
        urls={"next": "https://api.discogs.com/artists/3857/releases?page=3"},
    )


@pytest.mark.parametrize(
    "round_trip",
    [lambda r: pickle.loads(pickle.dumps(r)), copy.copy, copy.deepcopy],
    ids=["pickle", "copy", "deepcopy"],
)
def test_survives_pickle_and_copy(round_trip):
    result = _result()
    clone = round_trip(result)
    assert type(clone) is PageResult
    assert clone == result
    assert clone.items[0].title == "Pretty Hate Machine"


@pytest.mark.parametrize(
    "name", [field.name for field in dataclasses.fields(PageResult)]
)
def test_attributes_cannot_be_reassigned(name):
    result = _result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(result, name, None)
