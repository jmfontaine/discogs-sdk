"""Timestamp fields parse to aware datetimes; ``raw`` keeps what the API sent."""

from __future__ import annotations

import logging
import pickle
from datetime import datetime
from types import MappingProxyType

import pytest

from discogs_sdk import Export, Order, Release, User


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        # ISO 8601 with an offset, the common case.
        ("2004-04-30T08:10:05-07:00", "2004-04-30T08:10:05-07:00"),
        # Space instead of "T" (User.registered in the reference).
        ("2011-08-30 14:21:45-07:00", "2011-08-30T14:21:45-07:00"),
        # "-00:00" reads as UTC.
        ("2011-10-21T09:25:17-00:00", "2011-10-21T09:25:17+00:00"),
        # Naive: Pacific wall time, following daylight saving.
        ("2026-10-11T07:07:34", "2026-10-11T07:07:34-07:00"),
        ("2026-01-15T07:00:00", "2026-01-15T07:00:00-08:00"),
        # Naive inside the hour repeated when DST ends: the first (PDT) occurrence.
        ("2025-11-02T01:30:00", "2025-11-02T01:30:00-07:00"),
    ],
)
def test_every_observed_shape_parses_to_an_aware_datetime(
    sent: str, expected: str
) -> None:
    export = Export.model_validate({"id": 1, "created_ts": sent})
    assert export.created_at is not None
    assert export.created_at.isoformat() == expected
    assert export.raw["created_ts"] == sent
    # Any shape equals the same moment sent with its offset spelled out.
    explicit = Export.model_validate({"id": 1, "created_ts": expected})
    assert export.created_at == explicit.created_at


def test_naive_and_offset_values_compare() -> None:
    export = Export.model_validate({"id": 1, "created_ts": "2026-10-11T07:07:34"})
    user = User.model_validate(
        {"id": 1, "username": "trent_reznor", "registered": "2026-10-11 07:07:35-07:00"}
    )
    assert export.created_at is not None
    assert user.registered is not None
    assert export.created_at < user.registered


def test_empty_string_is_none_without_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="discogs_sdk"):
        release = Release.model_validate(
            {"id": 352665, "title": "The Downward Spiral", "date_added": ""}
        )
    assert release.date_added is None
    assert caplog.records == []


def test_unparseable_value_is_logged_and_kept_in_raw(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="discogs_sdk"):
        order = Order.model_validate(
            {
                "id": "1-1",
                "created": "2011-10-21T09:25:17-07:00",
                "last_activity": "yesterday",
            }
        )
    assert order.last_activity is None
    assert order.created is not None
    assert order.raw["last_activity"] == "yesterday"
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "Order.last_activity" in record.getMessage()
    assert "'yesterday'" in record.getMessage()


@pytest.mark.parametrize(
    "sent",
    [
        "2026-10-11T07:07:34",
        # Inside the hour repeated when DST ends.
        "2025-11-02T01:30:00",
        "2011-08-30 14:21:45-07:00",
        None,
    ],
)
def test_json_dump_round_trips(sent: str | None) -> None:
    export = Export.model_validate({"id": 1, "created_ts": sent})
    dumped = export.model_dump(mode="json")
    restored = Export.model_validate(dumped)
    # Equal although the two were validated from different payloads.
    assert restored == export
    assert restored.raw != export.raw
    if sent is not None:
        # The dump is normalized ISO 8601 with the offset made explicit.
        assert datetime.fromisoformat(dumped["created_at"]).tzinfo is not None


class TestRaw:
    def test_nested_models_expose_their_own_part(self) -> None:
        payload = {
            "id": 352665,
            "title": "The Downward Spiral",
            "extraartists": [{"name": "Flood", "anv": "Flood"}],
        }
        release = Release.model_validate(payload)
        assert release.raw is payload
        assert release.extra_artists is not None
        assert release.extra_artists[0].raw is payload["extraartists"][0]

    def test_any_mapping_input_is_kept(self) -> None:
        payload = MappingProxyType({"id": 352665, "title": "The Downward Spiral"})
        assert Release.model_validate(payload).raw is payload

    def test_raw_is_left_out_of_the_dump(self) -> None:
        release = Release.model_validate({"id": 352665, "title": "The Downward Spiral"})
        assert "raw" not in release.model_dump()

    def test_keyword_construction_reports_its_arguments(self) -> None:
        release = Release(id=352665, title="The Downward Spiral")
        assert release.raw == {"id": 352665, "title": "The Downward Spiral"}

    def test_model_built_without_validation_has_an_empty_payload(self) -> None:
        assert Release.model_construct(id=352665).raw == {}

    @pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
    def test_models_pickle_with_their_payload(self, protocol: int) -> None:
        release = Release.model_validate({"id": 352665, "title": "The Downward Spiral"})
        restored = pickle.loads(pickle.dumps(release, protocol=protocol))
        assert restored == release
        assert restored.raw == release.raw
