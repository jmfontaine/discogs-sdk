"""Integration tests for the search endpoint (read-only)."""

import pytest

from discogs_sdk.models.search import SearchResult

pytestmark = pytest.mark.integration


class TestSearch:
    def test_search_returns_results(self, client):
        page = client.search(query="Nine Inch Nails", type="artist")
        first = next(page)
        assert isinstance(first, SearchResult)
        assert isinstance(first.id, int)
        assert isinstance(first.title, str)

    def test_search_with_type_filter(self, client):
        page = client.search(query="The Downward Spiral", type="master")
        first = next(page)
        assert isinstance(first, SearchResult)
        assert first.type == "master"

    def test_search_pagination_fetches_first_page(self, client):
        page = client.search(query="Nine Inch Nails", type="release")
        first = next(page)
        assert isinstance(first, SearchResult)
        assert page._first_page_fetched
        assert len(page._items) > 0
