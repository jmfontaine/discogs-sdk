"""Behavioural regressions for the sequences the examples demonstrate.

tests/test_examples.py only parses and resolves imports. These exercise the
lifecycles and orderings that were previously wrong in examples/, under mocked
HTTP, so a regression fails here instead of in a user's terminal.
"""

from __future__ import annotations

import json

import httpx2
import pytest

from discogs_sdk import AsyncDiscogs, Discogs
from discogs_sdk._exceptions import DiscogsAPIError
from tests.conftest import (
    EXAMPLES_DIR,
    make_artist,
    make_artist_release,
    make_collection_instance_created,
    make_listing,
    make_listing_created,
    make_order,
    make_paginated_response,
    make_release,
)


class TestAsyncProxyVersusModel:
    """examples/async_usage.py: sub-resources live on the proxy, not the model."""

    async def test_proxy_survives_resolution_and_still_lists_releases(self, respx_mock):
        respx_mock.get("/artists/3857").respond(200, json=make_artist(id=3857))
        respx_mock.get("/artists/3857/releases").respond(
            200,
            json=make_paginated_response(
                "releases", [make_artist_release(title="The Downward Spiral")]
            ),
        )

        async with AsyncDiscogs(token="t") as client:
            artist_proxy = client.artists.get(3857)
            artist = await artist_proxy
            assert artist.name == "Nine Inch Nails"

            titles = [
                release.title
                async for release in artist_proxy.releases.list(sort="year")
            ]

        assert titles == ["The Downward Spiral"]

    async def test_resolved_model_has_no_sub_resources(self, respx_mock):
        respx_mock.get("/artists/3857").respond(200, json=make_artist(id=3857))

        async with AsyncDiscogs(token="t") as client:
            artist = await client.artists.get(3857)
            with pytest.raises(AttributeError):
                getattr(artist, "releases")  # noqa: B009


class TestCustomTransportLifecycle:
    """examples/advanced.py: the injected client outlives every SDK request."""

    def test_injected_client_stays_open_and_carries_sdk_headers(self, respx_mock):
        route = respx_mock.get("/releases/352665").respond(200, json=make_release())

        with httpx2.Client(headers={"X-App-Trace": "example"}) as custom_http:
            custom_client = Discogs(token="secret-token", http_client=custom_http)
            assert custom_client.releases.get(352665).title == "The Downward Spiral"
            custom_client.close()
            assert custom_http.is_closed is False

        request = route.calls[0].request
        assert request.headers["Authorization"] == "Discogs token=secret-token"
        assert request.headers["X-App-Trace"] == "example"
        assert custom_http.is_closed is True


class TestCollectionMutationOrder:
    """examples/collection.py: edit the created instance, then delete it."""

    def test_edits_the_returned_instance_before_deleting_it(self, respx_mock):
        folder_path = "/users/trent_reznor/collection/folders/1/releases"
        instance_path = f"{folder_path}/352665/instances/20"
        respx_mock.post(f"{folder_path}/352665").respond(
            201, json=make_collection_instance_created(instance_id=20)
        )
        respx_mock.post(instance_path).respond(204)
        respx_mock.post(f"{instance_path}/fields/1").respond(204)
        respx_mock.delete(instance_path).respond(204)

        with Discogs(token="t") as client:
            user = client.users.get("trent_reznor")
            created = user.collection.folders.get(1).releases.create(release_id=352665)
            instance_id = created.instance_id
            user.collection.folders.get(1).releases.get(352665).instances.update(
                instance_id, rating=5
            )
            user.collection.folders.get(1).releases.get(352665).instances.get(
                instance_id
            ).fields.update(field_id=1, value="Signed copy")
            user.collection.folders.get(1).releases.get(352665).instances.delete(
                instance_id
            )

        methods_and_paths = [
            (call.request.method, call.request.url.path) for call in respx_mock.calls
        ]
        assert methods_and_paths == [
            ("POST", f"{folder_path}/352665"),
            ("POST", instance_path),
            ("POST", f"{instance_path}/fields/1"),
            ("DELETE", instance_path),
        ]

    def test_a_failed_edit_still_removes_the_created_instance(self, respx_mock):
        folder_path = "/users/trent_reznor/collection/folders/1/releases"
        instance_path = f"{folder_path}/352665/instances/20"
        respx_mock.post(f"{folder_path}/352665").respond(
            201, json=make_collection_instance_created(instance_id=20)
        )
        respx_mock.post(instance_path).respond(422, json={"message": "Invalid rating"})
        deleted = respx_mock.delete(instance_path).respond(204)

        with Discogs(token="t") as client:
            user = client.users.get("trent_reznor")
            instances = user.collection.folders.get(1).releases.get(352665).instances
            instance_id = (
                user.collection.folders.get(1)
                .releases.create(release_id=352665)
                .instance_id
            )
            try:
                with pytest.raises(DiscogsAPIError):
                    instances.update(instance_id, rating=99)
            finally:
                instances.delete(instance_id)

        assert deleted.call_count == 1


class TestOrderUpdateSeparation:
    """examples/marketplace.py: status and shipping travel in separate requests."""

    def test_status_change_sends_status_only(self, respx_mock):
        route = respx_mock.post("/marketplace/orders/12345-1").respond(
            200, json=make_order(id="12345-1", status="Shipped")
        )

        with Discogs(token="t") as client:
            client.marketplace.orders.update("12345-1", status="Shipped")

        assert json.loads(route.calls[0].request.content) == {"status": "Shipped"}

    def test_shipping_change_sends_shipping_only(self, respx_mock):
        route = respx_mock.post("/marketplace/orders/12345-2").respond(
            200, json=make_order(id="12345-2", status="Invoice Sent")
        )

        with Discogs(token="t") as client:
            updated = client.marketplace.orders.update("12345-2", shipping=5.00)

        assert json.loads(route.calls[0].request.content) == {"shipping": 5.0}
        assert updated.status == "Invoice Sent"


class TestListingLifecycle:
    """examples/marketplace.py: update and delete the listing the create acknowledged."""

    def test_update_and_delete_use_the_acknowledged_listing_id(self, respx_mock):
        # Run the example's own Listings section, so a stale attribute in it fails.
        example = EXAMPLES_DIR / "marketplace.py"
        source = example.read_text()
        start = source.index("# ━━ Listings")
        # Blank lines in front keep tracebacks on the example's real line numbers.
        listings_section = (
            "\n" * source.count("\n", 0, start)
            + source[start : source.index("# ━━ Orders")]
        )
        respx_mock.get("/marketplace/listings/123456789").respond(
            200, json=make_listing(id=123456789)
        )
        respx_mock.post("/marketplace/listings").respond(
            201, json=make_listing_created(listing_id=41578241)
        )
        respx_mock.post("/marketplace/listings/41578241").respond(204)
        respx_mock.delete("/marketplace/listings/41578241").respond(204)

        with Discogs(token="t") as client:
            exec(  # noqa: S102
                compile(listings_section, str(example), "exec"), {"client": client}
            )

        methods_and_paths = [
            (call.request.method, call.request.url.path) for call in respx_mock.calls
        ]
        assert methods_and_paths == [
            ("GET", "/marketplace/listings/123456789"),
            ("POST", "/marketplace/listings"),
            ("POST", "/marketplace/listings/41578241"),
            ("DELETE", "/marketplace/listings/41578241"),
        ]
