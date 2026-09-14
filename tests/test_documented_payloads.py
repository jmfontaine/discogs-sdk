"""Every documented response key must be a declared field, not an extra.

``extra="allow"`` means an undocumented key and an unmodelled one look the same
after validation: both land in ``model_extra``, both are untyped, and reading
one that the response omitted raises ``AttributeError`` instead of returning
``None``. These tests walk each full-shape body from the reference and fail on
any key the model has not declared, at any depth, then push every documented
error body through the client to check the exception it raises.
"""

from __future__ import annotations

from typing import Any

import pytest
import respx
from pydantic import BaseModel

from discogs_sdk import AsyncDiscogs
from discogs_sdk._exceptions import DiscogsAPIError
from discogs_sdk.models._common import Price
from discogs_sdk.models.release import PriceSuggestions
from tests.conftest import BASE_URL
from tests.documented_payloads import (
    DOCUMENTED_ENVELOPES,
    DOCUMENTED_ERRORS,
    DOCUMENTED_PAYLOADS,
    PRICE_SUGGESTIONS,
)


def _undeclared(value: Any, path: str = "") -> list[str]:
    """Dotted paths of every key that landed in ``model_extra``, recursively."""
    found: list[str] = []
    if isinstance(value, BaseModel):
        prefix = f"{path}." if path else ""
        found += [f"{prefix}{key}" for key in value.model_extra or {}]
        for name in type(value).model_fields:
            found += _undeclared(getattr(value, name, None), f"{prefix}{name}")
    elif isinstance(value, list):
        for index, element in enumerate(value):
            found += _undeclared(element, f"{path}[{index}]")
    return found


@pytest.mark.parametrize(
    "name", sorted(n for n, e in DOCUMENTED_PAYLOADS.items() if not e.dynamic)
)
def test_documented_body_is_fully_declared(name: str) -> None:
    entry = DOCUMENTED_PAYLOADS[name]
    assert _undeclared(entry.model.model_validate(entry.payload)) == []


@pytest.mark.parametrize("name", sorted(DOCUMENTED_ENVELOPES))
def test_documented_envelope_items_are_fully_declared(name: str) -> None:
    item = DOCUMENTED_PAYLOADS[DOCUMENTED_ENVELOPES[name].item]
    assert _undeclared(item.model.model_validate(item.payload)) == []


def test_price_suggestions_expose_dynamic_condition_keys() -> None:
    """Suggested prices are keyed by condition, so those keys are data, not schema."""
    suggestions = PriceSuggestions.model_validate(PRICE_SUGGESTIONS)

    assert set(suggestions.conditions) == set(PRICE_SUGGESTIONS)
    assert all(isinstance(price, Price) for price in suggestions.conditions.values())
    assert suggestions["Mint (M)"].value == PRICE_SUGGESTIONS["Mint (M)"]["value"]
    with pytest.raises(KeyError):
        suggestions["Sealed"]


@pytest.mark.parametrize("name", sorted(DOCUMENTED_ERRORS))
async def test_documented_error_body_raises_its_exception(name: str) -> None:
    """The documented status decides the exception; the body becomes its message."""
    entry = DOCUMENTED_ERRORS[name]
    body = {"message": "You don't have permission to access this resource."}

    with respx.mock(base_url=BASE_URL, using="httpcore2") as mock:
        mock.get("/releases/352665").mock(
            return_value=respx.MockResponse(entry.status, json=body)
        )
        async with AsyncDiscogs(token="t", max_retries=0) as client:
            with pytest.raises(entry.error) as raised:
                await client.releases.get(352665)

    assert isinstance(raised.value, DiscogsAPIError)
    assert raised.value.status_code == entry.status
    assert str(raised.value) == f"{entry.status}: {body['message']}"
    assert raised.value.response_body == body


@pytest.mark.parametrize("name", sorted(DOCUMENTED_PAYLOADS))
def test_payload_entry_metadata_is_usable(name: str) -> None:
    """Each body records where it came from, and allowlists only keys it carries.

    ``scripts/check_endpoint_coverage.py`` resolves these against the reference,
    but that copy is git-ignored, so this is the only place the metadata itself
    is checked.
    """
    entry = DOCUMENTED_PAYLOADS[name]

    assert entry.examples, f"{name} claims no example"
    for example in entry.examples:
        assert example.doc.endswith(".md")
        assert example.section
        assert example.status.isdigit() or example.status == "request"
        assert example.ordinal >= 0
        assert example.id.startswith(f"{example.doc}::{example.section}::")
    assert len({e.id for e in entry.examples}) == len(entry.examples)

    for key in entry.extra_keys:
        node: Any = entry.payload
        for part in key.split("."):
            assert isinstance(node, dict) and part in node, (
                f"{name} allowlists {key!r}, which its payload does not carry"
            )
            node = node[part]


@pytest.mark.parametrize("name", sorted(DOCUMENTED_ENVELOPES))
def test_envelope_entry_points_at_a_registered_item(name: str) -> None:
    envelope = DOCUMENTED_ENVELOPES[name]

    assert envelope.example.section
    assert envelope.items_key
    assert envelope.item in DOCUMENTED_PAYLOADS
    if envelope.items_path:
        assert envelope.items_path[0] == envelope.items_key


@pytest.mark.parametrize("name", sorted(DOCUMENTED_ERRORS))
def test_error_entry_status_matches_its_example(name: str) -> None:
    entry = DOCUMENTED_ERRORS[name]

    assert str(entry.status) == entry.example.status
    assert issubclass(entry.error, DiscogsAPIError)
