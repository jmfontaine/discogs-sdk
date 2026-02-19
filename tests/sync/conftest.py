from __future__ import annotations

import pytest
import respx

from discogs_sdk import Discogs

from tests.conftest import BASE_URL


@pytest.fixture
def client(respx_mock):
    return Discogs(token="test-token")


@pytest.fixture
def no_retry_client(respx_mock):
    return Discogs(token="test-token", max_retries=0)


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL) as router:
        yield router
