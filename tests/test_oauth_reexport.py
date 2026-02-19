"""Test that the oauth.py re-export module is importable and exports all symbols."""

from __future__ import annotations


def test_reexport_symbols():
    from discogs_sdk.oauth import (
        AccessToken,
        RequestToken,
        async_get_access_token,
        async_get_request_token,
        get_access_token,
        get_request_token,
    )

    assert AccessToken is not None
    assert RequestToken is not None
    assert callable(get_request_token)
    assert callable(get_access_token)
    assert callable(async_get_request_token)
    assert callable(async_get_access_token)
