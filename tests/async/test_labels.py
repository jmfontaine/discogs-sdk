"""Tests for async Labels resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.label import Label, LabelRelease

from tests.conftest import make_label, make_label_release, make_paginated_response


class TestLabelsGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.labels.get(26011)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves_to_label(self, client, respx_mock):
        respx_mock.get("/labels/26011").mock(return_value=httpx.Response(200, json=make_label()))
        result = await client.labels.get(26011)
        assert isinstance(result, Label)
        assert result.name == "Nothing Records"


class TestLabelReleases:
    async def test_releases_list(self, client, respx_mock):
        items = [make_label_release(id=i) for i in range(2)]
        respx_mock.get("/labels/26011/releases").mock(
            return_value=httpx.Response(200, json=make_paginated_response("releases", items))
        )
        lazy = client.labels.get(26011)
        results = [item async for item in lazy.releases.list()]
        assert len(results) == 2
        assert all(isinstance(r, LabelRelease) for r in results)


class TestLabelModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/labels/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "L"}))
        result = await client.labels.get(1)
        assert result.id == 1

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/labels/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "L", "_unknown_extra_field": "test"})
        )
        result = await client.labels.get(1)
        assert result.model_extra["_unknown_extra_field"] == "test"
