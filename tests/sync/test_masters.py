"""Tests for sync Masters resource."""

from __future__ import annotations

import httpx

from discogs_sdk.models.master import MasterVersion

from tests.conftest import make_master, make_master_version, make_paginated_response


class TestMastersGet:
    def test_get_returns_lazy_no_http(self, client, respx_mock):
        _lazy = client.masters.get(5765)
        assert respx_mock.calls.call_count == 0

    def test_get_resolves_to_master(self, client, respx_mock):
        respx_mock.get("/masters/5765").mock(return_value=httpx.Response(200, json=make_master()))
        lazy = client.masters.get(5765)
        assert lazy.title == "The Downward Spiral"


class TestMasterVersions:
    def test_versions_accessible_without_http(self, client, respx_mock):
        lazy = client.masters.get(5765)
        _ = lazy.versions
        assert respx_mock.calls.call_count == 0

    def test_versions_list(self, client, respx_mock):
        items = [make_master_version(id=i) for i in range(2)]
        respx_mock.get("/masters/5765/versions").mock(
            return_value=httpx.Response(200, json=make_paginated_response("versions", items))
        )
        lazy = client.masters.get(5765)
        results = list(lazy.versions.list())
        assert len(results) == 2
        assert all(isinstance(v, MasterVersion) for v in results)

    def test_versions_list_with_params(self, client, respx_mock):
        respx_mock.get("/masters/5765/versions").mock(
            return_value=httpx.Response(200, json=make_paginated_response("versions", [make_master_version()]))
        )
        lazy = client.masters.get(5765)
        results = list(lazy.versions.list(format="Vinyl", country="US"))
        assert len(results) == 1
