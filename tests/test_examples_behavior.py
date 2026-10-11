"""Behavioural regressions for the examples.

The four examples that write to the API run here end to end under a strict respx
router: every request they make must be routed, every route must be used, and
the test pins the exact sequence of method, path and body. Editing a write in
an example (its arguments, its order, its cleanup) therefore fails a test here
instead of in a user's terminal. The remaining classes cover SDK behaviour an
example relies on.
"""

from __future__ import annotations

import contextlib
import email
import email.policy
import io
import json
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from respx.router import MockRouter

from discogs_sdk import AsyncDiscogs, Discogs, DiscogsAPIError
from tests.conftest import (
    EXAMPLES_DIR,
    make_artist,
    make_artist_release,
    make_collection_field,
    make_collection_folder,
    make_collection_instance_created,
    make_collection_value,
    make_community_rating,
    make_export,
    make_fee,
    make_label,
    make_label_release,
    make_list,
    make_list_summary,
    make_listing,
    make_listing_created,
    make_master,
    make_master_version,
    make_order,
    make_order_message,
    make_paginated_response,
    make_release,
    make_release_stats,
    make_search_result,
    make_upload,
    make_user,
    make_user_release_rating,
    make_want,
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


Sent = tuple[str, str, Any]


def _body(request: httpx2.Request) -> Any:
    """The request body: JSON decoded, a multipart upload as its parts, else None.

    An upload part becomes ``name: (filename, content type)``, which leaves out
    the random boundary and the file's bytes.
    """
    if not request.content:
        return None
    content_type = request.headers["Content-Type"]
    if not content_type.startswith("multipart/form-data"):
        return json.loads(request.content)
    message = email.message_from_bytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + request.content,
        policy=email.policy.HTTP,
    )
    return {
        part.get_param("name", header="content-disposition"): (
            part.get_filename(),
            part.get_content_type(),
        )
        for part in message.iter_parts()
    }


def _sent(router: MockRouter) -> list[Sent]:
    """Every request *router* received, in order, as (method, path, body)."""
    return [
        (call.request.method, call.request.url.path, _body(call.request))
        for call in router.calls
    ]


@pytest.fixture
def run_example(monkeypatch) -> Callable[[str], None]:
    """Run ``examples/<name>`` as a script with a fake token and silenced stdout."""
    monkeypatch.setenv("DISCOGS_TOKEN", "example-token")

    def run(name: str) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            namespace = runpy.run_path(str(EXAMPLES_DIR / name))
        # The examples end without closing their clients; close the ones still
        # bound, so advanced.py's SQLite cache does not outlive the test.
        for value in namespace.values():
            if isinstance(value, Discogs):
                value.close()

    return run


COLLECTION_USER = "/users/your_username"
FOLDERS = f"{COLLECTION_USER}/collection/folders"
NEW_FOLDER = f"{FOLDERS}/2"
FOLDER_RELEASE = f"{FOLDERS}/1/releases/352665"
INSTANCE = f"{FOLDER_RELEASE}/instances/20"
WANT = f"{COLLECTION_USER}/wants/352665"


def _collection_item() -> dict[str, Any]:
    return {
        "id": 352665,
        "instance_id": 20,
        "folder_id": 1,
        "rating": 5,
        "basic_information": {
            "id": 352665,
            "title": "The Downward Spiral",
            "artists": [make_artist(id=3857)],
        },
    }


def _route_collection_until_instance_edit(router: MockRouter) -> None:
    """Route examples/collection.py up to the release it adds to folder 1."""
    router.get(FOLDERS).respond(
        200,
        json={
            "folders": [
                make_collection_folder(id=0, name="All"),
                make_collection_folder(id=1, name="Uncategorized"),
            ]
        },
    )
    router.get(f"{FOLDERS}/1").respond(
        200, json=make_collection_folder(id=1, name="Uncategorized")
    )
    router.post(FOLDERS).respond(
        201, json=make_collection_folder(id=2, name="Industrial", count=0)
    )
    router.post(NEW_FOLDER).respond(
        200, json=make_collection_folder(id=2, name="Industrial / EBM", count=0)
    )
    router.delete(NEW_FOLDER).respond(204)
    router.get(f"{FOLDERS}/0/releases").respond(
        200, json=make_paginated_response("releases", [_collection_item()])
    )
    router.post(FOLDER_RELEASE).respond(
        201,
        json=make_collection_instance_created(instance_id=20, username="your_username"),
    )


COLLECTION_UNTIL_INSTANCE_EDIT: list[Sent] = [
    ("GET", FOLDERS, None),
    ("GET", f"{FOLDERS}/1", None),
    ("POST", FOLDERS, {"name": "Industrial"}),
    ("POST", NEW_FOLDER, {"name": "Industrial / EBM"}),
    ("DELETE", NEW_FOLDER, None),
    ("GET", f"{FOLDERS}/0/releases", None),
    ("POST", FOLDER_RELEASE, None),
]


class TestCollectionExample:
    """examples/collection.py: edit the created instance, then delete it."""

    def test_requests(self, respx_mock, run_example):
        _route_collection_until_instance_edit(respx_mock)
        respx_mock.post(INSTANCE).respond(204)
        respx_mock.get(f"{COLLECTION_USER}/collection/fields").respond(
            200, json={"fields": [make_collection_field(id=1, name="Notes")]}
        )
        respx_mock.post(f"{INSTANCE}/fields/1").respond(204)
        respx_mock.delete(INSTANCE).respond(204)
        respx_mock.get(f"{COLLECTION_USER}/collection/value").respond(
            200, json=make_collection_value()
        )
        respx_mock.get(f"{COLLECTION_USER}/collection/releases/352665").respond(
            200, json=make_paginated_response("releases", [_collection_item()])
        )
        respx_mock.get(f"{COLLECTION_USER}/wants").respond(
            200, json=make_paginated_response("wants", [make_want(id=352665)])
        )
        respx_mock.put(WANT).respond(201, json=make_want(id=352665))
        respx_mock.post(WANT).respond(
            200,
            json=make_want(
                id=352665, notes="Looking for original US pressing", rating=4
            ),
        )
        respx_mock.delete(WANT).respond(204)

        run_example("collection.py")

        assert _sent(respx_mock) == [
            *COLLECTION_UNTIL_INSTANCE_EDIT,
            ("POST", INSTANCE, {"rating": 5}),
            ("GET", f"{COLLECTION_USER}/collection/fields", None),
            ("POST", f"{INSTANCE}/fields/1", {"value": "Signed copy"}),
            ("DELETE", INSTANCE, None),
            ("GET", f"{COLLECTION_USER}/collection/value", None),
            ("GET", f"{COLLECTION_USER}/collection/releases/352665", None),
            ("GET", f"{COLLECTION_USER}/wants", None),
            ("PUT", WANT, None),
            (
                "POST",
                WANT,
                {"notes": "Looking for original US pressing", "rating": 4},
            ),
            ("DELETE", WANT, None),
        ]

    def test_a_failed_edit_still_removes_the_created_instance(
        self, respx_mock, run_example
    ):
        _route_collection_until_instance_edit(respx_mock)
        respx_mock.post(INSTANCE).respond(422, json={"message": "Invalid rating"})
        respx_mock.delete(INSTANCE).respond(204)

        with pytest.raises(DiscogsAPIError):
            run_example("collection.py")

        assert _sent(respx_mock) == [
            *COLLECTION_UNTIL_INSTANCE_EDIT,
            ("POST", INSTANCE, {"rating": 5}),
            ("DELETE", INSTANCE, None),
        ]


class TestMarketplaceExample:
    """examples/marketplace.py: listing lifecycle, order updates, a message."""

    def test_requests(self, respx_mock, run_example):
        respx_mock.get("/marketplace/listings/123456789").respond(
            200, json=make_listing(id=123456789)
        )
        respx_mock.post("/marketplace/listings").respond(
            201, json=make_listing_created(listing_id=41578241)
        )
        respx_mock.post("/marketplace/listings/41578241").respond(204)
        respx_mock.delete("/marketplace/listings/41578241").respond(204)
        respx_mock.get("/marketplace/orders/12345-1").respond(
            200, json=make_order(id="12345-1", status="Payment Received")
        )
        respx_mock.get("/marketplace/orders").respond(
            200,
            json=make_paginated_response(
                "orders", [make_order(id="12345-1", status="Payment Received")]
            ),
        )
        respx_mock.post("/marketplace/orders/12345-1").respond(
            200, json=make_order(id="12345-1", status="Shipped")
        )
        respx_mock.post("/marketplace/orders/12345-2").respond(
            200, json=make_order(id="12345-2", status="Invoice Sent")
        )
        respx_mock.get("/marketplace/orders/12345-1/messages").respond(
            200, json=make_paginated_response("messages", [make_order_message()])
        )
        respx_mock.post("/marketplace/orders/12345-1/messages").respond(
            201, json=make_order_message(message="Your order has shipped!")
        )
        respx_mock.get("/marketplace/fee/25.0").respond(200, json=make_fee())
        respx_mock.get("/marketplace/fee/25.0/EUR").respond(
            200, json=make_fee(currency="EUR")
        )
        respx_mock.get("/users/seller_username/inventory").respond(
            200, json=make_paginated_response("listings", [make_listing()])
        )

        run_example("marketplace.py")

        assert _sent(respx_mock) == [
            ("GET", "/marketplace/listings/123456789", None),
            (
                "POST",
                "/marketplace/listings",
                {
                    "release_id": 352665,
                    "condition": "Very Good Plus (VG+)",
                    "price": 25.0,
                    "status": "For Sale",
                },
            ),
            (
                "POST",
                "/marketplace/listings/41578241",
                {"condition": "Near Mint (NM or M-)", "price": 22.5},
            ),
            ("DELETE", "/marketplace/listings/41578241", None),
            ("GET", "/marketplace/orders/12345-1", None),
            ("GET", "/marketplace/orders", None),
            ("POST", "/marketplace/orders/12345-1", {"status": "Shipped"}),
            ("POST", "/marketplace/orders/12345-2", {"shipping": 5.0}),
            ("GET", "/marketplace/orders/12345-1/messages", None),
            (
                "POST",
                "/marketplace/orders/12345-1/messages",
                {
                    "message": "Your order has shipped! Tracking: 1Z999AA10123456784",
                    "status": "Shipped",
                },
            ),
            ("GET", "/marketplace/fee/25.0", None),
            ("GET", "/marketplace/fee/25.0/EUR", None),
            ("GET", "/users/seller_username/inventory", None),
            ("GET", "/users/seller_username/inventory", None),
        ]


class TestDatabaseExample:
    """examples/database.py: reads around one rating set and removed."""

    def test_requests(self, respx_mock, run_example):
        respx_mock.get("/releases/352665").respond(
            200,
            json={
                **make_release(id=352665),
                "artists": [make_artist(id=3857)],
            },
        )
        respx_mock.get("/releases/352665/rating").respond(
            200, json=make_community_rating(release_id=352665)
        )
        user_rating = make_user_release_rating(
            release_id=352665, username="your_username"
        )
        respx_mock.get("/releases/352665/rating/your_username").respond(
            200, json=user_rating
        )
        respx_mock.put("/releases/352665/rating/your_username").respond(
            201, json=user_rating
        )
        respx_mock.delete("/releases/352665/rating/your_username").respond(204)
        respx_mock.get("/releases/352665/stats").respond(200, json=make_release_stats())
        respx_mock.get("/marketplace/price_suggestions/352665").respond(
            200, json={"Mint (M)": {"currency": "USD", "value": 30.0}}
        )
        respx_mock.get("/marketplace/stats/352665").respond(
            200,
            json={
                "lowest_price": {"currency": "USD", "value": 20.0},
                "num_for_sale": 12,
                "blocked_from_sale": False,
            },
        )
        respx_mock.get("/artists/3857").respond(200, json=make_artist(id=3857))
        respx_mock.get("/artists/3857/releases").respond(
            200, json=make_paginated_response("releases", [make_artist_release()])
        )
        respx_mock.get("/masters/3719").respond(200, json=make_master(id=3719))
        respx_mock.get("/masters/3719/versions").respond(
            200, json=make_paginated_response("versions", [make_master_version()])
        )
        respx_mock.get("/labels/647").respond(200, json=make_label(id=647))
        respx_mock.get("/labels/647/releases").respond(
            200, json=make_paginated_response("releases", [make_label_release()])
        )
        respx_mock.get("/database/search").respond(
            200, json=make_paginated_response("results", [make_search_result()])
        )

        run_example("database.py")

        assert _sent(respx_mock) == [
            ("GET", "/releases/352665", None),
            ("GET", "/releases/352665/rating", None),
            ("GET", "/releases/352665/rating/your_username", None),
            ("PUT", "/releases/352665/rating/your_username", {"rating": 5}),
            ("DELETE", "/releases/352665/rating/your_username", None),
            ("GET", "/releases/352665/stats", None),
            ("GET", "/marketplace/price_suggestions/352665", None),
            ("GET", "/marketplace/stats/352665", None),
            ("GET", "/artists/3857", None),
            ("GET", "/artists/3857/releases", None),
            ("GET", "/masters/3719", None),
            ("GET", "/masters/3719/versions", None),
            ("GET", "/labels/647", None),
            ("GET", "/labels/647/releases", None),
            ("GET", "/database/search", None),
            ("GET", "/database/search", None),
        ]


class TestAdvancedExample:
    """examples/advanced.py: inventory uploads and a profile update among reads."""

    def test_requests(self, respx_mock, run_example, monkeypatch, tmp_path: Path):
        # The example's SQLite cache lives under Path.home(), and its export
        # download and uploads use the working directory. Patching Path.home
        # rather than HOME also holds on Windows, which reads USERPROFILE.
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.chdir(tmp_path)
        for name in ("add_items.csv", "update_items.csv", "delete_items.csv"):
            (tmp_path / name).write_text("release_id,price\n352665,25.00\n")

        respx_mock.get("/releases/999999999").respond(
            404, json={"message": "Release not found."}
        )
        respx_mock.get("/releases/352665").respond(200, json=make_release(id=352665))
        respx_mock.get("/artists/3857").respond(200, json=make_artist(id=3857))
        respx_mock.post("/inventory/export").respond(
            200, headers={"Location": "https://api.discogs.com/inventory/export/9"}
        )
        respx_mock.get("/inventory/export").respond(
            200, json=make_paginated_response("items", [make_export(id=9)])
        )
        respx_mock.get("/inventory/export/9").respond(
            200, json=make_export(id=9, status="success")
        )
        respx_mock.get("/inventory/export/9/download").respond(
            200, content=b"listing_id,release_id\n41578241,352665\n"
        )
        for kind, job_id in (("add", 11), ("change", 12), ("delete", 13)):
            respx_mock.post(f"/inventory/upload/{kind}").respond(
                200,
                headers={
                    "Location": f"https://api.discogs.com/inventory/upload/{job_id}"
                },
            )
        respx_mock.get("/inventory/upload").respond(
            200, json=make_paginated_response("items", [make_upload(id=11)])
        )
        respx_mock.get("/inventory/upload/11").respond(200, json=make_upload(id=11))
        respx_mock.get("/lists/12345").respond(200, json=make_list(id=12345))
        respx_mock.get("/users/jmfontaine/lists").respond(
            200, json=make_paginated_response("lists", [make_list_summary()])
        )
        respx_mock.get("/users/jmfontaine").respond(
            200, json=make_user(username="jmfontaine")
        )
        respx_mock.post("/users/your_username").respond(
            200, json=make_user(username="your_username")
        )
        respx_mock.get("/users/jmfontaine/contributions").respond(
            200,
            json=make_paginated_response("contributions", [make_release(id=352665)]),
        )
        respx_mock.get("/users/jmfontaine/submissions").respond(
            200,
            json={
                **make_paginated_response("submissions", []),
                "submissions": {
                    "artists": [make_artist(id=3857)],
                    "labels": [make_label(id=647)],
                    "releases": [make_release(id=352665)],
                },
            },
        )

        run_example("advanced.py")

        uploads = [
            ("add", "add_items.csv"),
            ("change", "update_items.csv"),
            ("delete", "delete_items.csv"),
        ]
        assert _sent(respx_mock) == [
            ("GET", "/releases/999999999", None),
            ("GET", "/releases/352665", None),
            ("GET", "/releases/352665", None),
            ("GET", "/artists/3857", None),
            ("GET", "/releases/352665", None),
            ("POST", "/inventory/export", None),
            ("GET", "/inventory/export", None),
            ("GET", "/inventory/export/9", None),
            ("GET", "/inventory/export/9/download", None),
            *[
                (
                    "POST",
                    f"/inventory/upload/{kind}",
                    {"upload": (filename, "text/csv")},
                )
                for kind, filename in uploads
            ],
            ("GET", "/inventory/upload", None),
            ("GET", "/inventory/upload/11", None),
            ("GET", "/lists/12345", None),
            ("GET", "/users/jmfontaine/lists", None),
            ("GET", "/users/jmfontaine", None),
            (
                "POST",
                "/users/your_username",
                {
                    "name": "New Display Name",
                    "location": "Brooklyn, NY",
                    "curr_abbr": "USD",
                },
            ),
            ("GET", "/users/jmfontaine/contributions", None),
            ("GET", "/users/jmfontaine/submissions", None),
            ("GET", "/users/jmfontaine/submissions", None),
            ("GET", "/users/jmfontaine/submissions", None),
        ]
