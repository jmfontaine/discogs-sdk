"""Tests for sync client logging in _send()."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from discogs_sdk import Discogs
from discogs_sdk._exceptions import DiscogsConnectionError, RateLimitError

from tests.conftest import BASE_URL, make_release


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL) as router:
        yield router


@pytest.fixture
def client(respx_mock):
    return Discogs(token="test-token", max_retries=3)


class TestRequestResponseLogging:
    def test_logs_request_and_response(self, client, respx_mock, caplog):
        respx_mock.get("/releases/1").mock(return_value=httpx.Response(200, json=make_release()))

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018 — triggers resolve

        request_logs = [r for r in caplog.records if r.message.startswith("HTTP request:")]
        response_logs = [r for r in caplog.records if r.message.startswith("HTTP response:")]

        assert len(request_logs) == 1
        assert "GET" in request_logs[0].message
        assert "/releases/1" in request_logs[0].message
        assert request_logs[0].levelno == logging.DEBUG

        assert len(response_logs) == 1
        assert "200" in response_logs[0].message
        assert "ms" in response_logs[0].message
        assert response_logs[0].levelno == logging.DEBUG


class TestRetryLogging:
    def test_logs_retry_on_429(self, client, respx_mock, caplog, monkeypatch):
        responses = iter(
            [
                httpx.Response(429, json={"message": "Rate limited"}),
                httpx.Response(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))
        monkeypatch.setattr("time.sleep", lambda _: None)

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018

        retry_logs = [r for r in caplog.records if r.message.startswith("Retrying")]
        assert len(retry_logs) == 1
        assert retry_logs[0].levelno == logging.INFO
        assert "status 429" in retry_logs[0].message
        assert "attempt 2/4" in retry_logs[0].message

    def test_logs_retry_on_5xx(self, client, respx_mock, caplog, monkeypatch):
        responses = iter(
            [
                httpx.Response(502, text="Bad Gateway"),
                httpx.Response(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))
        monkeypatch.setattr("time.sleep", lambda _: None)

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018

        retry_logs = [r for r in caplog.records if r.message.startswith("Retrying")]
        assert len(retry_logs) == 1
        assert "status 502" in retry_logs[0].message

    def test_logs_multiple_retries(self, client, respx_mock, caplog, monkeypatch):
        responses = iter(
            [
                httpx.Response(500, json={"message": "Error"}),
                httpx.Response(503, text="Service Unavailable"),
                httpx.Response(200, json=make_release()),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))
        monkeypatch.setattr("time.sleep", lambda _: None)

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018

        retry_logs = [r for r in caplog.records if r.message.startswith("Retrying")]
        assert len(retry_logs) == 2
        assert "attempt 2/4" in retry_logs[0].message
        assert "attempt 3/4" in retry_logs[1].message

    def test_no_retry_log_on_exhaustion(self, respx_mock, caplog, monkeypatch):
        """When retries are exhausted, there should be no retry log for the final attempt."""
        client = Discogs(token="test-token", max_retries=1)
        responses = iter(
            [
                httpx.Response(429, json={"message": "Rate limited"}),
                httpx.Response(429, json={"message": "Rate limited"}, headers={"Retry-After": "10"}),
            ]
        )
        respx_mock.get("/releases/1").mock(side_effect=lambda req: next(responses))
        monkeypatch.setattr("time.sleep", lambda _: None)

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            with pytest.raises(RateLimitError):
                lazy.title  # noqa: B018

        retry_logs = [r for r in caplog.records if r.message.startswith("Retrying")]
        assert len(retry_logs) == 1
        assert "attempt 2/2" in retry_logs[0].message


class TestConnectionErrorLogging:
    def test_logs_retry_on_connection_error(self, client, respx_mock, caplog, monkeypatch):
        call_count = 0

        def side_effect(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json=make_release())

        respx_mock.get("/releases/1").mock(side_effect=side_effect)
        monkeypatch.setattr("time.sleep", lambda _: None)

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018

        retry_logs = [r for r in caplog.records if r.message.startswith("Retrying")]
        assert len(retry_logs) == 1
        assert retry_logs[0].levelno == logging.INFO
        assert "connection error" in retry_logs[0].message

    def test_logs_final_connection_error(self, respx_mock, caplog, monkeypatch):
        client = Discogs(token="test-token", max_retries=1)
        respx_mock.get("/releases/1").mock(side_effect=httpx.ConnectError("Connection refused"))
        monkeypatch.setattr("time.sleep", lambda _: None)

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            with pytest.raises(DiscogsConnectionError):
                lazy.title  # noqa: B018

        error_logs = [r for r in caplog.records if "connection error after" in r.message.lower()]
        assert len(error_logs) == 1
        assert error_logs[0].levelno == logging.DEBUG


class TestNoSensitiveDataLogged:
    def test_auth_token_not_in_logs(self, client, respx_mock, caplog):
        respx_mock.get("/releases/1").mock(return_value=httpx.Response(200, json=make_release()))

        with caplog.at_level(logging.DEBUG, logger="discogs_sdk"):
            lazy = client.releases.get(1)
            lazy.title  # noqa: B018

        full_log = " ".join(r.message for r in caplog.records)
        assert "test-token" not in full_log
