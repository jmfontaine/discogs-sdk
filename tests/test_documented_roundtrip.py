"""Round-trip tests: documented full-shape bodies through the real client.

Each test mocks one documented example, verbatim from
``tests/documented_payloads.py``, and drives it through the public
``AsyncDiscogs``/``Discogs`` client so URL construction, envelope extraction
and lazy-proxy resolution are exercised — not just ``model_validate``. Every
test asserts a typed nested (or aliased) attribute that only exists because
the corresponding field is declared on the model.
"""

from __future__ import annotations

import pytest
import respx

from discogs_sdk import AsyncDiscogs, Discogs
from discogs_sdk.models.artist import Artist, ArtistRelease
from discogs_sdk.models.collection import (
    CollectionField,
    CollectionFolder,
    CollectionInstanceCreated,
    CollectionItem,
    CollectionValue_,
)
from discogs_sdk.models.export import Export
from discogs_sdk.models.label import Label, LabelRelease
from discogs_sdk.models.list_ import List_, ListSummary
from discogs_sdk.models.marketplace import Fee, Listing, Order, OrderMessage
from discogs_sdk.models.master import Master, MasterVersion
from discogs_sdk.models.release import (
    CommunityRating,
    MarketplaceReleaseStats,
    PriceSuggestions,
    Release,
    ReleaseStats,
    UserReleaseRating,
)
from discogs_sdk.models.search import SearchResult
from discogs_sdk.models.upload import Upload
from discogs_sdk.models.user import Identity, User
from discogs_sdk.models.wantlist import Want
from tests.conftest import make_paginated_response
from tests.documented_payloads import (
    ADDED_WANT,
    ARTIST,
    ARTIST_RELEASE,
    BASE_URL,
    COLLECTION_FIELD,
    COLLECTION_FOLDER,
    COLLECTION_INSTANCE_CREATED,
    COLLECTION_RELEASE_ITEM,
    COLLECTION_VALUE,
    COMMUNITY_RATING,
    DOCUMENTED_ENVELOPES,
    DOCUMENTED_PAYLOADS,
    EXPORT,
    FEE,
    IDENTITY,
    IMAGE_URL,
    INVENTORY_LISTING,
    LABEL,
    LIST_DETAIL,
    LIST_SUMMARY,
    LISTING,
    LISTING_CREATED,
    MARKETPLACE_RELEASE_STATS,
    MASTER,
    ORDER,
    PAGINATION_MIDDLE,
    PAGINATION_SINGLE,
    PRICE_SUGGESTIONS,
    RELEASE,
    RELEASE_STATS,
    SEARCH_RESULT,
    SUBMITTED_RELEASE,
    UPLOAD,
    USER,
    USER_RELEASE_RATING,
)


@pytest.fixture
def respx_mock():
    with respx.mock(base_url=BASE_URL, using="httpcore2") as router:
        yield router


@pytest.fixture
def client(respx_mock):
    return AsyncDiscogs(token="test-token")


@pytest.fixture
def sync_client(respx_mock):
    return Discogs(token="test-token")


def _envelope_body(name: str) -> dict:
    """Wrap one documented item payload in the envelope shape it belongs to.

    Looks the item payload up through ``DOCUMENTED_PAYLOADS`` /
    ``DOCUMENTED_ENVELOPES`` so the body always matches what the registry
    claims, rather than a hand-copied literal.
    """
    envelope = DOCUMENTED_ENVELOPES[name]
    item_payload = DOCUMENTED_PAYLOADS[envelope.item].payload
    if envelope.items_path:
        pagination = {"page": 1, "pages": 1, "per_page": 50, "items": 1, "urls": {}}
        container: dict = {}
        node = container
        for key in envelope.items_path[:-1]:
            node[key] = {}
            node = node[key]
        node[envelope.items_path[-1]] = [item_payload]
        return {"pagination": pagination, **container}
    return make_paginated_response(envelope.items_key, [item_payload])


# Bodies with no public endpoint of their own: each is reached through the
# parent body that embeds it, or through an endpoint another body already
# covers. Splitting a fixture without deciding which side of this line it falls
# on fails ``test_every_documented_body_is_accounted_for``.
EMBEDDED_ONLY = frozenset(
    {
        "collection_basic_information",
        "wantlist_basic_information",
        # Item bodies exercised through their envelope's endpoint.
        "artist_release",
        "label_release",
        "list_summary",
        "listed_order",
        "master_version",
        "order_message",
        "search_result",
        "submitted_release",
    }
)

ROUND_TRIPPED = frozenset(
    {
        "added_want",
        "artist",
        "collection_field",
        "collection_folder",
        "collection_item",
        "collection_release_item",
        "collection_instance_created",
        "collection_value",
        "community_rating",
        "export",
        "fee",
        "identity",
        "inventory_listing",
        "label",
        "list_detail",
        "listing",
        "listing_created",
        "marketplace_release_stats",
        "master",
        "order",
        "price_suggestions",
        "release",
        "release_stats",
        "upload",
        "user",
        "user_release_rating",
        "want",
    }
)


def test_every_documented_body_is_accounted_for() -> None:
    """A new or split fixture must be round-tripped, or declared embedded."""
    assert ROUND_TRIPPED | EMBEDDED_ONLY == set(DOCUMENTED_PAYLOADS)
    assert not ROUND_TRIPPED & EMBEDDED_ONLY


class TestReleaseRoundTrip:
    async def test_get(self, client, respx_mock):
        respx_mock.get("/releases/352665").mock(
            return_value=respx.MockResponse(200, json=RELEASE)
        )
        result = await client.releases.get(352665)
        assert isinstance(result, Release)
        assert result.community.have == 25185
        assert result.extra_artists[0].role == "Producer, Written-By"

    async def test_rating(self, client, respx_mock):
        respx_mock.get("/releases/352665/rating").mock(
            return_value=respx.MockResponse(200, json=COMMUNITY_RATING)
        )
        lazy = client.releases.get(352665)
        result = await lazy.rating.get()
        assert isinstance(result, CommunityRating)
        assert result.rating.average == 4.62

    async def test_user_rating_get(self, client, respx_mock):
        respx_mock.get("/releases/352665/rating/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=USER_RELEASE_RATING)
        )
        lazy = client.releases.get(352665)
        result = await lazy.rating.get("trent_reznor")
        assert isinstance(result, UserReleaseRating)
        assert result.rating == 5

    async def test_user_rating_update(self, client, respx_mock):
        respx_mock.put("/releases/352665/rating/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=USER_RELEASE_RATING)
        )
        lazy = client.releases.get(352665)
        result = await lazy.rating.update("trent_reznor", 5)
        assert isinstance(result, UserReleaseRating)
        assert result.release_id == 352665

    async def test_stats(self, client, respx_mock):
        respx_mock.get("/releases/352665/stats").mock(
            return_value=respx.MockResponse(200, json=RELEASE_STATS)
        )
        lazy = client.releases.get(352665)
        result = await lazy.stats.get()
        assert isinstance(result, ReleaseStats)
        assert result.num_have == 25185

    async def test_price_suggestions(self, client, respx_mock):
        respx_mock.get("/marketplace/price_suggestions/352665").mock(
            return_value=respx.MockResponse(200, json=PRICE_SUGGESTIONS)
        )
        lazy = client.releases.get(352665)
        result = await lazy.price_suggestions.get()
        assert isinstance(result, PriceSuggestions)
        assert result.conditions["Mint (M)"].value == 39.99

    async def test_marketplace_stats(self, client, respx_mock):
        respx_mock.get("/marketplace/stats/352665").mock(
            return_value=respx.MockResponse(200, json=MARKETPLACE_RELEASE_STATS)
        )
        lazy = client.releases.get(352665)
        result = await lazy.marketplace_stats.get()
        assert isinstance(result, MarketplaceReleaseStats)
        assert result.lowest_price.value == 24.99


class TestMasterRoundTrip:
    async def test_get(self, client, respx_mock):
        respx_mock.get("/masters/3719").mock(
            return_value=respx.MockResponse(200, json=MASTER)
        )
        result = await client.masters.get(3719)
        assert isinstance(result, Master)
        assert result.tracklist[0].extra_artists[0].role == "Producer, Written-By"

    async def test_versions_list(self, client, respx_mock):
        respx_mock.get("/masters/3719/versions").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("master_versions"))
        )
        lazy = client.masters.get(3719)
        results = [item async for item in lazy.versions.list()]
        assert len(results) == 1
        assert isinstance(results[0], MasterVersion)
        assert results[0].stats.community.in_collection == 25185


class TestArtistRoundTrip:
    async def test_get(self, client, respx_mock):
        respx_mock.get("/artists/3857").mock(
            return_value=respx.MockResponse(200, json=ARTIST)
        )
        result = await client.artists.get(3857)
        assert isinstance(result, Artist)
        assert result.members[0].active is True

    async def test_releases_list(self, client, respx_mock):
        respx_mock.get("/artists/3857/releases").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("artist_releases"))
        )
        lazy = client.artists.get(3857)
        results = [item async for item in lazy.releases.list()]
        assert len(results) == 1
        assert isinstance(results[0], ArtistRelease)
        assert results[0].role == ARTIST_RELEASE["role"]


class TestLabelRoundTrip:
    async def test_get(self, client, respx_mock):
        respx_mock.get("/labels/647").mock(
            return_value=respx.MockResponse(200, json=LABEL)
        )
        result = await client.labels.get(647)
        assert isinstance(result, Label)
        assert result.sub_labels[0].name == "Nothing Interactive"

    async def test_releases_list(self, client, respx_mock):
        respx_mock.get("/labels/647/releases").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("label_releases"))
        )
        lazy = client.labels.get(647)
        results = [item async for item in lazy.releases.list()]
        assert len(results) == 1
        assert isinstance(results[0], LabelRelease)
        assert results[0].catalog_number == "HALO EIGHT"


class TestSearchRoundTrip:
    async def test_search(self, client, respx_mock):
        respx_mock.get("/database/search").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("search"))
        )
        results = [item async for item in client.search(query="Downward Spiral")]
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].community.have == SEARCH_RESULT["community"]["have"]


class TestMarketplaceRoundTrip:
    async def test_listing_get(self, client, respx_mock):
        respx_mock.get("/marketplace/listings/172723812").mock(
            return_value=respx.MockResponse(200, json=LISTING)
        )
        result = await client.marketplace.listings.get(172723812)
        assert isinstance(result, Listing)
        assert result.original_shipping_price.value == 2.5

    async def test_listing_create(self, client, respx_mock):
        respx_mock.post("/marketplace/listings").mock(
            return_value=respx.MockResponse(201, json=LISTING_CREATED)
        )
        created = await client.marketplace.listings.create(
            release_id=352665, condition="Mint (M)", price=39.99
        )
        assert isinstance(created, Listing)
        # The acknowledgement identifies the listing as "listing_id".
        assert created.id == LISTING_CREATED["listing_id"]

    async def test_order_get(self, client, respx_mock):
        respx_mock.get("/marketplace/orders/1-1").mock(
            return_value=respx.MockResponse(200, json=ORDER)
        )
        result = await client.marketplace.orders.get("1-1")
        assert isinstance(result, Order)
        assert result.tracking.carrier == "UPS"

    async def test_orders_list(self, client, respx_mock):
        respx_mock.get("/marketplace/orders").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("orders"))
        )
        results = [item async for item in client.marketplace.orders.list()]
        assert len(results) == 1
        assert isinstance(results[0], Order)
        assert results[0].items[0].release.thumbnail == IMAGE_URL

    async def test_order_messages_list(self, client, respx_mock):
        respx_mock.get("/marketplace/orders/1-1/messages").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("order_messages"))
        )
        lazy = client.marketplace.orders.get("1-1")
        results = [item async for item in lazy.messages.list()]
        assert len(results) == 1
        assert isinstance(results[0], OrderMessage)
        assert results[0].refund.amount == 5.0

    async def test_fee_get(self, client, respx_mock):
        respx_mock.get("/marketplace/fee/42.0").mock(
            return_value=respx.MockResponse(200, json=FEE)
        )
        result = await client.marketplace.fee.get(price=42.0)
        assert isinstance(result, Fee)
        assert result.value == 0.42
        assert result.currency == "USD"


class TestUserRoundTrip:
    async def test_get(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor").mock(
            return_value=respx.MockResponse(200, json=USER)
        )
        result = await client.users.get("trent_reznor")
        assert isinstance(result, User)
        assert result.currency_code == "USD"

    async def test_inventory_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/inventory").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("inventory"))
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.inventory.list()]
        assert len(results) == 1
        assert isinstance(results[0], Listing)
        assert results[0].release.artist == INVENTORY_LISTING["release"]["artist"]

    async def test_submissions_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/submissions").mock(
            return_value=respx.MockResponse(
                200, json=_envelope_body("user_submissions")
            )
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.submissions.list()]
        assert len(results) == 1
        assert isinstance(results[0], Release)
        assert results[0].community.have == SUBMITTED_RELEASE["community"]["have"]

    async def test_contributions_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/contributions").mock(
            return_value=respx.MockResponse(
                200, json=_envelope_body("user_contributions")
            )
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.contributions.list()]
        assert len(results) == 1
        assert isinstance(results[0], Release)
        assert results[0].labels[0].resource_url == f"{BASE_URL}/labels/647"

    async def test_lists_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/lists").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("user_lists"))
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.lists.list()]
        assert len(results) == 1
        assert isinstance(results[0], ListSummary)
        assert results[0].description == LIST_SUMMARY["description"]

    async def test_collection_folders_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/folders").mock(
            return_value=respx.MockResponse(200, json={"folders": [COLLECTION_FOLDER]})
        )
        lazy = client.users.get("trent_reznor")
        results = await lazy.collection.folders.list()
        assert len(results) == 1
        assert isinstance(results[0], CollectionFolder)
        assert results[0].resource_url == COLLECTION_FOLDER["resource_url"]

    async def test_collection_folder_releases_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/folders/1/releases").mock(
            return_value=respx.MockResponse(
                200, json=_envelope_body("collection_items_by_folder")
            )
        )
        lazy = client.users.get("trent_reznor")
        folder = lazy.collection.folders.get(1)
        results = [item async for item in folder.releases.list()]
        assert len(results) == 1
        assert isinstance(results[0], CollectionItem)
        assert results[0].notes[0].field_id == 1

    async def test_collection_fields_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/fields").mock(
            return_value=respx.MockResponse(200, json={"fields": [COLLECTION_FIELD]})
        )
        lazy = client.users.get("trent_reznor")
        results = await lazy.collection.fields.list()
        assert len(results) == 1
        assert isinstance(results[0], CollectionField)
        assert results[0].options == COLLECTION_FIELD["options"]

    async def test_collection_add_release_to_folder(self, client, respx_mock):
        respx_mock.post(
            "/users/trent_reznor/collection/folders/1/releases/352665"
        ).mock(return_value=respx.MockResponse(201, json=COLLECTION_INSTANCE_CREATED))
        lazy = client.users.get("trent_reznor")
        created = await lazy.collection.folders.get(1).releases.create(
            release_id=352665
        )
        assert isinstance(created, CollectionInstanceCreated)
        assert created.instance_id == 45274429

    async def test_collection_value(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/collection/value").mock(
            return_value=respx.MockResponse(200, json=COLLECTION_VALUE)
        )
        lazy = client.users.get("trent_reznor")
        value = await lazy.collection.value.get()
        assert isinstance(value, CollectionValue_)
        assert value.median == COLLECTION_VALUE["median"]

    async def test_wantlist_list(self, client, respx_mock):
        respx_mock.get("/users/trent_reznor/wants").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("wantlist"))
        )
        lazy = client.users.get("trent_reznor")
        results = [item async for item in lazy.wantlist.list()]
        assert len(results) == 1
        assert isinstance(results[0], Want)
        assert results[0].basic_information.formats[0].text == "180 Gram"

    async def test_wantlist_create(self, client, respx_mock):
        respx_mock.put("/users/trent_reznor/wants/352665").mock(
            return_value=respx.MockResponse(201, json=ADDED_WANT)
        )
        lazy = client.users.get("trent_reznor")
        result = await lazy.wantlist.create(release_id=352665, rating=5)
        assert isinstance(result, Want)
        assert result.basic_information.labels[0].entity_type_name == "Label"

    async def test_wantlist_update(self, client, respx_mock):
        respx_mock.post("/users/trent_reznor/wants/352665").mock(
            return_value=respx.MockResponse(200, json=ADDED_WANT)
        )
        lazy = client.users.get("trent_reznor")
        result = await lazy.wantlist.update(352665, notes="Original US pressing")
        assert isinstance(result, Want)
        assert result.basic_information.labels[0].catalog_number == "HALO EIGHT"

    async def test_lists_get(self, client, respx_mock):
        respx_mock.get("/lists/1").mock(
            return_value=respx.MockResponse(200, json=LIST_DETAIL)
        )
        result = await client.lists.get(1)
        assert isinstance(result, List_)
        assert result.items[0].image_url == IMAGE_URL


class TestUserNamespaceRoundTrip:
    async def test_identity(self, client, respx_mock):
        respx_mock.get("/oauth/identity").mock(
            return_value=respx.MockResponse(200, json=IDENTITY)
        )
        result = await client.user.identity()
        assert isinstance(result, Identity)
        assert result.consumer_name == "NINApp"

    async def test_exports_get(self, client, respx_mock):
        respx_mock.get("/inventory/export/599632").mock(
            return_value=respx.MockResponse(200, json=EXPORT)
        )
        result = await client.exports.get(599632)
        assert isinstance(result, Export)
        assert result.created_at == EXPORT["created_ts"]

    async def test_exports_list(self, client, respx_mock):
        respx_mock.get("/inventory/export").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("recent_exports"))
        )
        results = [item async for item in client.exports.list()]
        assert len(results) == 1
        assert isinstance(results[0], Export)
        assert results[0].filename == EXPORT["filename"]

    async def test_uploads_get(self, client, respx_mock):
        respx_mock.get("/inventory/upload/599632").mock(
            return_value=respx.MockResponse(200, json=UPLOAD)
        )
        result = await client.uploads.get(599632)
        assert isinstance(result, Upload)
        assert result.finished_at == UPLOAD["finished_ts"]

    async def test_uploads_list(self, client, respx_mock):
        respx_mock.get("/inventory/upload").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("recent_uploads"))
        )
        results = [item async for item in client.uploads.list()]
        assert len(results) == 1
        assert isinstance(results[0], Upload)
        assert results[0].results == UPLOAD["results"]


class TestPaginationMetadata:
    """Home.md documents all four pagination URLs on a middle page, and a
    single page that carries none of them. Iteration stops after the first
    page in both cases so the paginator never chases a real "next" URL.
    """

    async def test_middle_page(self, client, respx_mock):
        body = {"pagination": PAGINATION_MIDDLE, "releases": [COLLECTION_RELEASE_ITEM]}
        respx_mock.get("/users/trent_reznor/collection/releases/352665").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        ref = client.users.get("trent_reznor").collection.releases.get(352665)
        page = ref.list()
        results = []
        async for item in page:
            results.append(item)
            break
        assert len(results) == 1
        assert isinstance(results[0], CollectionItem)
        urls = PAGINATION_MIDDLE["urls"]
        assert page.page == 2
        assert page.per_page == 75
        assert page.total_items == 2255
        assert page.total_pages == 30
        assert page.first_url == urls["first"]
        assert page.prev_url == urls["prev"]
        assert page.next_url == urls["next"]
        assert page.last_url == urls["last"]
        assert respx_mock.calls.call_count == 1

    async def test_single_page(self, client, respx_mock):
        body = {"pagination": PAGINATION_SINGLE, "releases": [COLLECTION_RELEASE_ITEM]}
        respx_mock.get("/users/trent_reznor/collection/releases/352665").mock(
            return_value=respx.MockResponse(200, json=body)
        )
        ref = client.users.get("trent_reznor").collection.releases.get(352665)
        page = ref.list()
        results = [item async for item in page]
        assert len(results) == 1
        assert page.page == 1
        assert page.per_page == 50
        assert page.total_items == 1
        assert page.total_pages == 1
        assert page.first_url is None
        assert page.prev_url is None
        assert page.next_url is None
        assert page.last_url is None
        assert respx_mock.calls.call_count == 1


class TestSyncRoundTrip:
    """Spot checks proving the generated sync path resolves the same
    documented bodies as the async path: a release, a paginated list and a
    lazy sub-resource.
    """

    def test_release_get(self, sync_client, respx_mock):
        respx_mock.get("/releases/352665").mock(
            return_value=respx.MockResponse(200, json=RELEASE)
        )
        result = sync_client.releases.get(352665)
        assert result.community.have == 25185
        assert result.title == RELEASE["title"]

    def test_master_versions_list(self, sync_client, respx_mock):
        respx_mock.get("/masters/3719/versions").mock(
            return_value=respx.MockResponse(200, json=_envelope_body("master_versions"))
        )
        lazy = sync_client.masters.get(3719)
        results = list(lazy.versions.list())
        assert len(results) == 1
        assert isinstance(results[0], MasterVersion)
        assert results[0].stats.community.in_collection == 25185

    def test_release_rating_lazy_subresource(self, sync_client, respx_mock):
        respx_mock.get("/releases/352665/rating").mock(
            return_value=respx.MockResponse(200, json=COMMUNITY_RATING)
        )
        lazy = sync_client.releases.get(352665)
        result = lazy.rating.get()
        assert result.rating.average == 4.62
        assert result.release_id == 352665

    def test_fee_get_resolves_on_attribute_access(self, sync_client, respx_mock):
        respx_mock.get("/marketplace/fee/42.0").mock(
            return_value=respx.MockResponse(200, json=FEE)
        )
        result = sync_client.marketplace.fee.get(price=42.0)
        assert respx_mock.calls.call_count == 0
        assert result.value == 0.42
        assert respx_mock.calls.call_count == 1
