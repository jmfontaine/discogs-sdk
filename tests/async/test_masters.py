"""Tests for async Masters resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.master import Master, MasterVersion

from tests.conftest import make_master, make_master_version, make_paginated_response


class TestMastersGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.masters.get(5765)
        assert respx_mock.calls.call_count == 0

    async def test_get_resolves_to_master(self, client, respx_mock):
        respx_mock.get("/masters/5765").mock(return_value=httpx.Response(200, json=make_master()))
        result = await client.masters.get(5765)
        assert isinstance(result, Master)
        assert result.title == "The Downward Spiral"


class TestMasterVersions:
    def test_versions_accessible_without_http(self, client, respx_mock):
        lazy = client.masters.get(5765)
        _ = lazy.versions
        assert respx_mock.calls.call_count == 0

    async def test_versions_list(self, client, respx_mock):
        items = [make_master_version(id=i) for i in range(2)]
        respx_mock.get("/masters/5765/versions").mock(
            return_value=httpx.Response(200, json=make_paginated_response("versions", items))
        )
        lazy = client.masters.get(5765)
        results = [item async for item in lazy.versions.list()]
        assert len(results) == 2
        assert all(isinstance(v, MasterVersion) for v in results)

    async def test_versions_list_with_params(self, client, respx_mock):
        respx_mock.get("/masters/5765/versions").mock(
            return_value=httpx.Response(200, json=make_paginated_response("versions", [make_master_version()]))
        )
        lazy = client.masters.get(5765)
        results = [
            item async for item in lazy.versions.list(format="Vinyl", country="US", sort="released", sort_order="asc")
        ]
        assert len(results) == 1

    async def test_none_params_filtered(self, client, respx_mock):
        respx_mock.get("/masters/5765/versions").mock(
            return_value=httpx.Response(200, json=make_paginated_response("versions", [make_master_version()]))
        )
        lazy = client.masters.get(5765)
        # None values should be filtered out, not sent as "None"
        results = [item async for item in lazy.versions.list(format=None)]
        assert len(results) == 1


class TestMasterModel:
    async def test_required_fields(self, client, respx_mock):
        respx_mock.get("/masters/1").mock(return_value=httpx.Response(200, json={"id": 1, "title": "T"}))
        result = await client.masters.get(1)
        assert result.id == 1
        assert result.year is None

    async def test_extra_allow(self, client, respx_mock):
        respx_mock.get("/masters/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "title": "T", "_unknown_extra_field": "test"})
        )
        result = await client.masters.get(1)
        assert result.model_extra["_unknown_extra_field"] == "test"
