"""Tests for sync Labels resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.label import LabelRelease

from tests.conftest import make_label, make_label_release, make_paginated_response


class TestLabelsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.labels.get(26011)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves_to_label(self, client, respx_mock):
        respx_mock.get("/labels/26011").mock(return_value=httpx.Response(200, json=make_label()))
        lazy = client.labels.get(26011)
        assert lazy.name == "Nothing Records"


class TestLabelReleases:
    def test_releases_list(self, client, respx_mock):
        items = [make_label_release(id=i) for i in range(2)]
        respx_mock.get("/labels/26011/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", items))
        )
        lazy = client.labels.get(26011)
        results = list(lazy.releases.list())
        assert len(results) == 2
        assert all(isinstance(r, LabelRelease) for r in results)
