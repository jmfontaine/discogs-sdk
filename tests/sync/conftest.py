from __future__ import annotations

import pytest

from discogs_sdk import Discogs


@pytest.fixture
def client(respx_mock):
    return Discogs(token="test-token")


@pytest.fixture
def no_retry_client(respx_mock):
    return Discogs(token="test-token", max_retries=0)
