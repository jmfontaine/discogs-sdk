"""Integration tests for sub-resources and pagination (read-only)."""

import pytest

from discogs_sdk.models.artist import ArtistRelease
from discogs_sdk.models.label import LabelRelease
from discogs_sdk.models.master import MasterVersion

from tests.integration.conftest import ARTIST_ID, LABEL_ID, MASTER_ID, RELEASE_ID

pytestmark = pytest.mark.integration


class TestArtistReleases:
    def test_list_returns_artist_releases(self, client):
        page = client.artists.get(ARTIST_ID).releases.list()
        first = next(page)
        assert isinstance(first, ArtistRelease)
        assert isinstance(first.id, int)
        assert isinstance(first.title, str)


class TestMasterVersions:
    def test_list_returns_versions(self, client):
        page = client.masters.get(MASTER_ID).versions.list()
        first = next(page)
        assert isinstance(first, MasterVersion)
        assert isinstance(first.id, int)
        assert isinstance(first.title, str)


class TestLabelReleases:
    def test_list_returns_label_releases(self, client):
        page = client.labels.get(LABEL_ID).releases.list()
        first = next(page)
        assert isinstance(first, LabelRelease)
        assert isinstance(first.id, int)
        assert isinstance(first.title, str)


class TestReleaseCommunityRating:
    def test_get_community_rating(self, client):
        result = client.releases.get(RELEASE_ID).rating.get()
        assert result.release_id == RELEASE_ID
        assert isinstance(result.rating.average, float)
        assert isinstance(result.rating.count, int)


class TestReleaseStats:
    def test_get_release_stats(self, client):
        result = client.releases.get(RELEASE_ID).stats.get()
        # The stats endpoint returns null for num_have/num_want with personal
        # tokens (only OAuth consumer-key apps get real values). Just verify
        # the response parses and the fields exist.
        assert hasattr(result, "num_have")
        assert hasattr(result, "num_want")


class TestReleaseMarketplaceStats:
    def test_get_marketplace_stats(self, client):
        result = client.releases.get(RELEASE_ID).marketplace_stats.get()
        assert isinstance(result.num_for_sale, int)


class TestReleasePriceSuggestions:
    def test_get_price_suggestions(self, client):
        result = client.releases.get(RELEASE_ID).price_suggestions.get()
        # PriceSuggestions uses extra="allow" for dynamic condition keys.
        # At minimum, the object should resolve without error.
        assert result is not None
