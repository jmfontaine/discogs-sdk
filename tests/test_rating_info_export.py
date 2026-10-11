"""`RatingInfo` is the type of `CommunityRating.rating`, so it is public API."""

from __future__ import annotations

import pydantic
import pytest

import discogs_sdk
import discogs_sdk.models
from discogs_sdk.models.release import CommunityRating, RatingInfo


@pytest.mark.parametrize("module", [discogs_sdk, discogs_sdk.models])
def test_rating_info_is_exported(module):
    assert module.RatingInfo is RatingInfo
    assert "RatingInfo" in module.__all__


@pytest.mark.parametrize("rating", [{"average": 4.5}, {"count": 3}])
def test_rating_info_keeps_average_and_count_required(rating):
    with pytest.raises(pydantic.ValidationError):
        CommunityRating.model_validate({"rating": rating, "release_id": 1})
