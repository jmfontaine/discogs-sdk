"""Integration tests for core database endpoints (read-only)."""

import pytest

from tests.integration.conftest import ARTIST_ID, LABEL_ID, MASTER_ID, RELEASE_ID

pytestmark = pytest.mark.integration


class TestRelease:
    def test_get_release(self, client):
        release = client.releases.get(RELEASE_ID)
        assert release.id == RELEASE_ID
        assert release.title == "The Downward Spiral"
        assert release.year == 1994
        assert release.country == "US"

    def test_release_has_tracklist(self, client):
        release = client.releases.get(RELEASE_ID)
        assert release.tracklist is not None
        assert len(release.tracklist) > 0
        assert release.tracklist[0].title is not None

    def test_release_has_artists(self, client):
        release = client.releases.get(RELEASE_ID)
        assert release.artists is not None
        names = [a.name for a in release.artists]
        assert "Nine Inch Nails" in names

    def test_release_has_genres(self, client):
        release = client.releases.get(RELEASE_ID)
        assert release.genres is not None
        assert len(release.genres) > 0


class TestArtist:
    def test_get_artist(self, client):
        artist = client.artists.get(ARTIST_ID)
        assert artist.id == ARTIST_ID
        assert artist.name == "Nine Inch Nails"

    def test_artist_has_profile(self, client):
        artist = client.artists.get(ARTIST_ID)
        assert isinstance(artist.profile, str)
        assert len(artist.profile) > 0

    def test_artist_has_members(self, client):
        artist = client.artists.get(ARTIST_ID)
        assert artist.members is not None
        assert len(artist.members) > 0


class TestMaster:
    def test_get_master(self, client):
        master = client.masters.get(MASTER_ID)
        assert master.id == MASTER_ID
        assert master.title == "The Downward Spiral"
        assert master.year == 1994

    def test_master_has_tracklist(self, client):
        master = client.masters.get(MASTER_ID)
        assert master.tracklist is not None
        assert len(master.tracklist) > 0


class TestLabel:
    def test_get_label(self, client):
        label = client.labels.get(LABEL_ID)
        assert label.id == LABEL_ID
        assert label.name == "Nothing Records"

    def test_label_has_profile(self, client):
        label = client.labels.get(LABEL_ID)
        assert isinstance(label.profile, str)
