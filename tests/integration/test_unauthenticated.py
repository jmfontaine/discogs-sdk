"""Integration tests for anonymous access (read-only).

No credentials at all. These pin what Discogs serves without authentication,
which is the part of the API that drifts silently: the SDK's models allow extra
fields, so a server-side change shows up as missing data rather than an error.

Anonymous traffic is limited to 25 requests/min per IP, and the authenticated
suite draws on the same IP budget: running both in one minute earns a 429 here.
Hence the ``unauthenticated`` marker, which keeps these out of
``just test-integration`` and onto their own CI runner. Keep the module small
for the same reason.
"""

import pytest

from discogs_sdk import AuthenticationError, Discogs
from discogs_sdk.models.search import SearchResult
from tests.integration.conftest import RELEASE_ID

pytestmark = [pytest.mark.integration, pytest.mark.unauthenticated]


@pytest.fixture
def anonymous():
    """A client with no credentials.

    ``tests/conftest.py::_clean_discogs_env`` removes every ``DISCOGS_*``
    variable before each test, so this stays anonymous even when the developer's
    shell exports a token. A leak would not pass silently either:
    ``test_user_scoped_endpoint_requires_authentication`` only holds without
    credentials.
    """
    with Discogs() as client:
        yield client


class TestPublicData:
    def test_release_is_readable(self, anonymous):
        release = anonymous.releases.get(RELEASE_ID)
        assert release.id == RELEASE_ID
        assert release.title == "The Downward Spiral"
        assert release.tracklist

    def test_release_includes_image_urls(self, anonymous):
        """Full resources carry images even without credentials.

        Discogs used to reserve image URLs for authenticated clients. It no
        longer does for resource reads (only search results are stripped), and
        this pins that so a return to the old behaviour is visible.
        """
        release = anonymous.releases.get(RELEASE_ID)
        assert release.images
        assert release.images[0].uri.startswith("https://")


class TestSearch:
    def test_search_is_open_to_anonymous_clients(self, anonymous):
        first = next(anonymous.search(query="Nine Inch Nails", type="artist"))
        assert isinstance(first, SearchResult)
        assert first.id == 3857

    def test_search_results_omit_image_urls(self, anonymous):
        """The one image difference authentication still makes.

        Anonymous search results come back with empty ``cover_image``/``thumb``
        strings; ``tests/integration/test_search.py`` asserts the authenticated
        half of this contract.
        """
        first = next(anonymous.search(query="Nine Inch Nails", type="artist"))
        assert first.cover_image == ""
        assert first.thumb == ""


class TestUserScopedEndpoints:
    def test_identity_requires_authentication(self, anonymous):
        with pytest.raises(AuthenticationError):
            anonymous.user.identity()
