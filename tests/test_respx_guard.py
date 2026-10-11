"""The suite refuses to run when respx cannot patch httpx2.

Without the ``httpcore2`` mocker, ``respx.mock(using="httpcore2")`` patches nothing
and mocked tests send their requests to the real Discogs API.
"""

from __future__ import annotations

import pytest
from respx.mocks import Mocker

from tests.conftest import require_httpcore2_mocker


def test_fails_when_the_httpcore2_mocker_is_missing(monkeypatch):
    registry = dict(Mocker.registry)
    del registry["httpcore2"]
    monkeypatch.setattr(Mocker, "registry", registry)

    with pytest.raises(RuntimeError) as excinfo:
        require_httpcore2_mocker()

    message = str(excinfo.value)
    assert '"httpcore2" mocker is not registered' in message
    assert "pytest-httpx2" in message
    assert "-p no:pytest_httpx2" in message
