"""One full-shape response body per example in the official API reference.

Every key here appears in the matching example in ``docs/discogs_api/``; the
values are rewritten with Nine Inch Nails data because that reference copy is
git-ignored for copyright reasons and cannot be vendored. The registry at the
bottom records where each body came from, so
``scripts/check_endpoint_coverage.py`` can re-derive the documented key sets and
compare them both ways wherever the reference is present. A body may only carry
a key its example lacks by declaring it in ``extra_keys``.

The minimal factories in ``conftest.py`` stay minimal: they keep endpoint tests
readable. These bodies exist to prove no documented key falls through to
``extra="allow"``, which is how nine typed fields went missing before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from discogs_sdk._exceptions import (
    AuthenticationError,
    DiscogsAPIError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from discogs_sdk.models._common import BasicInformation
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

BASE_URL = "https://api.discogs.com"
IMAGE_URL = "https://i.discogs.com/halo-eight.jpeg"

ARTIST_CREDIT: dict[str, Any] = {
    "anv": "NIN",
    "id": 3857,
    "join": "",
    "name": "Nine Inch Nails",
    "resource_url": f"{BASE_URL}/artists/3857",
    "role": "",
    "tracks": "",
}

EXTRA_ARTIST: dict[str, Any] = {
    "anv": "T. Reznor",
    "id": 4567,
    "join": "",
    "name": "Trent Reznor",
    "resource_url": f"{BASE_URL}/artists/4567",
    "role": "Producer, Written-By",
    "tracks": "",
}

IMAGE: dict[str, Any] = {
    "height": 600,
    "resource_url": IMAGE_URL,
    "type": "primary",
    "uri": IMAGE_URL,
    "uri150": IMAGE_URL,
    "width": 600,
}

VIDEO: dict[str, Any] = {
    "description": "Nine Inch Nails - Closer",
    "duration": 373,
    "embed": True,
    "title": "Nine Inch Nails - Closer",
    "uri": "https://www.youtube.com/watch?v=PTFwQP86BRs",
}

# Release, collection and wantlist bodies all embed this shape; only the
# companies list on a release adds "entity_type_name".
LABEL_CREDIT: dict[str, Any] = {
    "catno": "HALO EIGHT",
    "entity_type": "1",
    "id": 647,
    "name": "Nothing Records",
    "resource_url": f"{BASE_URL}/labels/647",
}

FORMAT: dict[str, Any] = {
    "descriptions": ["LP", "Album"],
    "name": "Vinyl",
    "qty": "2",
}

RELEASE: dict[str, Any] = {
    "artists": [ARTIST_CREDIT],
    "community": {
        "contributors": [{"resource_url": f"{BASE_URL}/users/nin", "username": "nin"}],
        "data_quality": "Correct",
        "have": 25185,
        "rating": {"average": 4.62, "count": 1994},
        "status": "Accepted",
        "submitter": {"resource_url": f"{BASE_URL}/users/nin", "username": "nin"},
        "want": 8721,
    },
    "companies": [
        {
            "catno": "",
            "entity_type": "13",
            "entity_type_name": "Phonographic Copyright (p)",
            "id": 647,
            "name": "Nothing Records",
            "resource_url": f"{BASE_URL}/labels/647",
        }
    ],
    "country": "US",
    "data_quality": "Correct",
    "date_added": "2004-04-30T08:10:05-07:00",
    "date_changed": "2012-12-03T02:50:12-07:00",
    "estimated_weight": 460,
    "extraartists": [EXTRA_ARTIST],
    "format_quantity": 2,
    "formats": [FORMAT],
    "genres": ["Electronic", "Rock"],
    "id": 352665,
    "identifiers": [{"type": "Barcode", "value": "6144826"}],
    "images": [IMAGE],
    "labels": [LABEL_CREDIT],
    "lowest_price": 24.99,
    "master_id": 3719,
    "master_url": f"{BASE_URL}/masters/3719",
    "notes": "Recorded at Le Pig, Los Angeles.",
    "num_for_sale": 58,
    "released": "1994-03-08",
    "released_formatted": "08 Mar 1994",
    "resource_url": f"{BASE_URL}/releases/352665",
    "series": [LABEL_CREDIT],
    "status": "Accepted",
    "styles": ["Industrial", "Alternative Rock"],
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
    "tracklist": [
        {
            "duration": "4:56",
            "position": "A1",
            "title": "Mr Self Destruct",
            "type_": "track",
        }
    ],
    "uri": "https://www.discogs.com/release/352665",
    "videos": [VIDEO],
    "year": 1994,
}

MASTER: dict[str, Any] = {
    "artists": [ARTIST_CREDIT],
    "data_quality": "Correct",
    "genres": ["Electronic", "Rock"],
    "id": 3719,
    "images": [IMAGE],
    "lowest_price": 9.36,
    "main_release": 352665,
    "main_release_url": f"{BASE_URL}/releases/352665",
    "num_for_sale": 9,
    "resource_url": f"{BASE_URL}/masters/3719",
    "styles": ["Industrial"],
    "title": "The Downward Spiral",
    "tracklist": [
        {
            "duration": "4:56",
            "extraartists": [EXTRA_ARTIST],
            "position": "1",
            "title": "Mr Self Destruct",
            "type_": "track",
        }
    ],
    "uri": "https://www.discogs.com/master/3719",
    "versions_url": f"{BASE_URL}/masters/3719/versions",
    "videos": [VIDEO],
    "year": 1994,
}

MASTER_VERSION: dict[str, Any] = {
    "catno": "HALO EIGHT",
    "country": "US",
    "format": "2×LP, 33 ⅓ RPM",
    "id": 352665,
    "label": "Nothing Records",
    "major_formats": ["Vinyl"],
    "released": "1994",
    "resource_url": f"{BASE_URL}/releases/352665",
    "stats": {
        "community": {"in_collection": 25185, "in_wantlist": 8721},
        "user": {"in_collection": 1, "in_wantlist": 0},
    },
    "status": "Accepted",
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
}

ARTIST: dict[str, Any] = {
    "data_quality": "Needs Vote",
    "id": 3857,
    "images": [IMAGE],
    "members": [
        {
            "active": True,
            "id": 4567,
            "name": "Trent Reznor",
            "resource_url": f"{BASE_URL}/artists/4567",
        }
    ],
    "name": "Nine Inch Nails",
    "namevariations": ["NIN", "Nine Inch Nails (NIN)"],
    "profile": "American industrial rock project formed in Cleveland in 1988.",
    "releases_url": f"{BASE_URL}/artists/3857/releases",
    "resource_url": f"{BASE_URL}/artists/3857",
    "uri": "https://www.discogs.com/artist/3857",
    "urls": ["https://www.nin.com/"],
}

ARTIST_RELEASE: dict[str, Any] = {
    "artist": "Nine Inch Nails",
    "format": "2×LP, Album",
    "id": 3719,
    "label": "Nothing Records",
    "main_release": 352665,
    "resource_url": f"{BASE_URL}/masters/3719",
    "role": "Main",
    "status": "Accepted",
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
    "type": "master",
    "year": 1994,
}

LABEL: dict[str, Any] = {
    "contact_info": "Nothing Records\nLos Angeles, CA\n",
    "data_quality": "Correct",
    "id": 647,
    "images": [IMAGE],
    "name": "Nothing Records",
    "profile": "American record label founded by Trent Reznor and John Malm Jr.",
    "releases_url": f"{BASE_URL}/labels/647/releases",
    "resource_url": f"{BASE_URL}/labels/647",
    "sublabels": [
        {
            "id": 26011,
            "name": "Nothing Interactive",
            "resource_url": f"{BASE_URL}/labels/26011",
        }
    ],
    "uri": "https://www.discogs.com/label/647",
    "urls": ["https://www.nothingrecords.com/"],
}

LABEL_RELEASE: dict[str, Any] = {
    "artist": "Nine Inch Nails",
    "catno": "HALO EIGHT",
    "format": "2×LP, Album",
    "id": 352665,
    "resource_url": f"{BASE_URL}/releases/352665",
    "status": "Accepted",
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
    "year": 1994,
}

SEARCH_RESULT: dict[str, Any] = {
    "barcode": ["6144826"],
    "catno": "HALO EIGHT",
    "community": {"have": 25185, "want": 8721},
    "country": "US",
    "format": ["Vinyl", "LP", "Album"],
    "genre": ["Electronic", "Rock"],
    "id": 352665,
    "label": ["Nothing Records"],
    "resource_url": f"{BASE_URL}/releases/352665",
    "style": ["Industrial"],
    "thumb": IMAGE_URL,
    "title": "Nine Inch Nails - The Downward Spiral",
    "type": "release",
    "uri": "/release/352665",
    "year": "1994",
}

# The collection body carries genres and styles; the wantlist body carries a
# format "text" instead. Neither is a superset of the other.
COLLECTION_BASIC_INFORMATION: dict[str, Any] = {
    "artists": [ARTIST_CREDIT],
    "cover_image": IMAGE_URL,
    "formats": [FORMAT],
    "genres": ["Electronic", "Rock"],
    "id": 352665,
    "labels": [LABEL_CREDIT],
    "resource_url": f"{BASE_URL}/releases/352665",
    "styles": ["Industrial"],
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
    "year": 1994,
}

WANTLIST_BASIC_INFORMATION: dict[str, Any] = {
    "artists": [ARTIST_CREDIT],
    "cover_image": IMAGE_URL,
    "formats": [FORMAT | {"text": "180 Gram"}],
    "id": 352665,
    "labels": [LABEL_CREDIT],
    "resource_url": f"{BASE_URL}/releases/352665",
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
    "year": 1994,
}

COLLECTION_ITEM: dict[str, Any] = {
    "basic_information": COLLECTION_BASIC_INFORMATION,
    "folder_id": 1,
    "id": 352665,
    "instance_id": 45274429,
    "notes": [{"field_id": 1, "value": "Mint (M)"}],
    "rating": 5,
}

COLLECTION_FOLDER: dict[str, Any] = {
    "count": 20,
    "id": 1,
    "name": "Uncategorized",
    "resource_url": f"{BASE_URL}/users/trent_reznor/collection/folders/1",
}

COLLECTION_FIELD: dict[str, Any] = {
    "id": 1,
    "lines": 3,
    "name": "Media Condition",
    "options": ["Mint (M)", "Near Mint (NM or M-)"],
    "position": 1,
    "public": True,
    "type": "dropdown",
}

COLLECTION_VALUE: dict[str, Any] = {
    "maximum": "$150.00",
    "median": "$45.00",
    "minimum": "$24.99",
}

COLLECTION_INSTANCE_CREATED: dict[str, Any] = {
    "instance_id": 45274429,
    "resource_url": (
        f"{BASE_URL}/users/trent_reznor/collection/folders/1"
        "/releases/352665/instances/45274429"
    ),
}

WANT: dict[str, Any] = {
    "basic_information": WANTLIST_BASIC_INFORMATION,
    "id": 352665,
    "notes": "Original US pressing wanted",
    "rating": 5,
    "resource_url": f"{BASE_URL}/users/trent_reznor/wants/352665",
}

# Adding to the wantlist echoes a different basic_information than the feed:
# labels spell out entity_type_name, and formats carry no "text".
ADDED_WANT_BASIC_INFORMATION: dict[str, Any] = {
    "artists": [ARTIST_CREDIT],
    "cover_image": IMAGE_URL,
    "formats": [FORMAT],
    "id": 352665,
    "labels": [LABEL_CREDIT | {"entity_type_name": "Label"}],
    "resource_url": f"{BASE_URL}/releases/352665",
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
    "year": 1994,
}

ADDED_WANT: dict[str, Any] = {
    "basic_information": ADDED_WANT_BASIC_INFORMATION,
    "id": 352665,
    "notes": "Original US pressing wanted",
    "rating": 5,
    "resource_url": f"{BASE_URL}/users/trent_reznor/wants/352665",
}

LISTING: dict[str, Any] = {
    "allow_offers": False,
    "audio": False,
    "comments": "Still sealed.",
    "condition": "Mint (M)",
    # Owner-only keys, and in_cart for any authenticated user: the section
    # documents these in prose rather than in its example body.
    "external_id": "HALO-8-SHELF-A",
    "format_quantity": 2,
    "in_cart": False,
    "location": "Shelf A",
    "quantity": 3,
    "weight": 460.0,
    "id": 172723812,
    "original_price": {
        "curr_abbr": "USD",
        "curr_id": 1,
        "formatted": "$120.00",
        "value": 120.0,
    },
    "original_shipping_price": {
        "curr_abbr": "USD",
        "curr_id": 1,
        "formatted": "$2.50",
        "value": 2.5,
    },
    "posted": "2014-07-15T12:55:01-07:00",
    "price": {"currency": "USD", "value": 120.0},
    "release": {
        "catalog_number": "HALO EIGHT",
        "description": "Nine Inch Nails - The Downward Spiral (2xLP, Album)",
        "id": 352665,
        "resource_url": f"{BASE_URL}/releases/352665",
        "thumbnail": IMAGE_URL,
        "year": 1994,
    },
    "resource_url": f"{BASE_URL}/marketplace/listings/172723812",
    "seller": {
        "avatar_url": IMAGE_URL,
        "id": 1369620,
        "payment": "PayPal",
        "resource_url": f"{BASE_URL}/users/trent_reznor",
        "shipping": "Buyer responsible for shipping.",
        "stats": {"rating": "100", "stars": 5.0, "total": 15},
        "url": f"{BASE_URL}/users/trent_reznor",
        "username": "trent_reznor",
    },
    "shipping_price": {"currency": "USD", "value": 2.5},
    "ships_from": "United States",
    "sleeve_condition": "Mint (M)",
    "status": "For Sale",
    "uri": "https://www.discogs.com/sell/item/172723812",
}

INVENTORY_LISTING: dict[str, Any] = {
    "allow_offers": False,
    "audio": False,
    "comments": "Still sealed.",
    "condition": "Mint (M)",
    "id": 172723812,
    "posted": "2014-07-15T12:55:01-07:00",
    "price": {"currency": "USD", "value": 120.0},
    "release": {
        "artist": "Nine Inch Nails",
        "catalog_number": "HALO EIGHT",
        "description": "Nine Inch Nails - The Downward Spiral (2xLP, Album)",
        "format": "(2xLP, Album)",
        "id": 352665,
        "resource_url": f"{BASE_URL}/releases/352665",
        "thumbnail": IMAGE_URL,
        "title": "The Downward Spiral",
        "year": 1994,
    },
    "resource_url": f"{BASE_URL}/marketplace/listings/172723812",
    "seller": {
        "id": 1369620,
        "resource_url": f"{BASE_URL}/users/trent_reznor",
        "username": "trent_reznor",
    },
    "ships_from": "United States",
    "sleeve_condition": "Mint (M)",
    "status": "For Sale",
    "uri": "https://www.discogs.com/sell/item/172723812",
}

LISTING_CREATED: dict[str, Any] = {
    "listing_id": 41578241,
    "resource_url": f"{BASE_URL}/marketplace/listings/41578241",
}

ORDER: dict[str, Any] = {
    "additional_instructions": "Please use sturdy packaging.",
    "archived": False,
    "buyer": {
        "id": 2,
        "resource_url": f"{BASE_URL}/users/halo_collector",
        "username": "halo_collector",
    },
    "created": "2011-10-21T09:25:17-07:00",
    "fee": {"currency": "USD", "value": 2.52},
    "id": "1-1",
    "items": [
        {
            "id": 41578242,
            "media_condition": "Mint (M)",
            "price": {"currency": "USD", "value": 42.0},
            "release": {
                "description": "Nine Inch Nails - The Downward Spiral (2xLP)",
                "id": 352665,
            },
            "sleeve_condition": "Near Mint (NM or M-)",
        }
    ],
    "last_activity": "2011-10-21T09:25:17-07:00",
    "messages_url": f"{BASE_URL}/marketplace/orders/1-1/messages",
    "next_status": ["New Order", "Buyer Contacted", "Invoice Sent"],
    "resource_url": f"{BASE_URL}/marketplace/orders/1-1",
    "seller": {
        "id": 1,
        "resource_url": f"{BASE_URL}/users/trent_reznor",
        "username": "trent_reznor",
    },
    "shipping": {"currency": "USD", "method": "Standard", "value": 5.0},
    "shipping_address": "Trent Reznor\n10050 Cielo Drive\nLos Angeles, CA\n",
    "status": "New Order",
    "total": {"currency": "USD", "value": 42.0},
    "tracking": {
        "carrier": "UPS",
        "number": "1Z999999999999999",
        "url": "https://www.ups.com/track?tracknum=1Z999999999999999",
    },
    "uri": "https://www.discogs.com/sell/order/1-1",
}

LISTED_ORDER: dict[str, Any] = {
    "additional_instructions": "Please use sturdy packaging.",
    "archived": False,
    "buyer": {
        "id": 2,
        "resource_url": f"{BASE_URL}/users/halo_collector",
        "username": "halo_collector",
    },
    "created": "2011-10-21T09:25:17-07:00",
    "fee": {"currency": "USD", "value": 2.52},
    "id": "1-1",
    "items": [
        {
            "id": 41578242,
            "price": {"currency": "USD", "value": 42.0},
            "release": {
                "description": "Nine Inch Nails - The Downward Spiral (2xLP)",
                "id": 352665,
                "resource_url": f"{BASE_URL}/releases/352665",
                "thumbnail": IMAGE_URL,
            },
        }
    ],
    "last_activity": "2011-10-21T09:25:17-07:00",
    "messages_url": f"{BASE_URL}/marketplace/orders/1-1/messages",
    "next_status": ["New Order", "Buyer Contacted", "Invoice Sent"],
    "resource_url": f"{BASE_URL}/marketplace/orders/1-1",
    "seller": {
        "id": 1,
        "resource_url": f"{BASE_URL}/users/trent_reznor",
        "username": "trent_reznor",
    },
    "shipping": {"currency": "USD", "method": "Standard", "value": 5.0},
    "shipping_address": "Trent Reznor\n10050 Cielo Drive\nLos Angeles, CA\n",
    "status": "New Order",
    "total": {"currency": "USD", "value": 42.0},
    "uri": "https://www.discogs.com/sell/order/1-1",
}

# The message log mixes variants — plain message, status change, shipping
# change, refund — and the reference documents them as one heterogeneous list.
ORDER_MESSAGE: dict[str, Any] = {
    "actor": {
        "resource_url": f"{BASE_URL}/users/trent_reznor",
        "username": "trent_reznor",
    },
    "from": {
        "avatar_url": IMAGE_URL,
        "id": 1001,
        "resource_url": f"{BASE_URL}/users/trent_reznor",
        "username": "trent_reznor",
    },
    "message": "Thank you for your order!",
    "new": 5.0,
    "order": {"id": "1-1", "resource_url": f"{BASE_URL}/marketplace/orders/1-1"},
    "original": 0.0,
    "refund": {
        "amount": 5.0,
        "order": {"id": "1-1", "resource_url": f"{BASE_URL}/marketplace/orders/1-1"},
    },
    "status_id": 6,
    "subject": "Discogs Order #1-1, The Downward Spiral",
    "timestamp": "2015-06-02T13:17:07-07:00",
    "type": "message",
}

FEE: dict[str, Any] = {"currency": "USD", "value": 0.42}

MARKETPLACE_RELEASE_STATS: dict[str, Any] = {
    "blocked_from_sale": False,
    "lowest_price": {"currency": "USD", "value": 24.99},
    "num_for_sale": 26,
}

COMMUNITY_RATING: dict[str, Any] = {
    "rating": {"average": 4.62, "count": 1994},
    "release_id": 352665,
}

USER_RELEASE_RATING: dict[str, Any] = {
    "rating": 5,
    "release_id": 352665,
    "username": "trent_reznor",
}

RELEASE_STATS: dict[str, Any] = {"num_have": 25185, "num_want": 8721}

IDENTITY: dict[str, Any] = {
    "consumer_name": "NINApp",
    "id": 1,
    "resource_url": f"{BASE_URL}/users/trent_reznor",
    "username": "trent_reznor",
}

USER: dict[str, Any] = {
    "avatar_url": IMAGE_URL,
    "banner_url": IMAGE_URL,
    "buyer_num_ratings": 12,
    "buyer_rating": 100.0,
    "buyer_rating_stars": 5.0,
    "collection_fields_url": f"{BASE_URL}/users/trent_reznor/collection/fields",
    "collection_folders_url": f"{BASE_URL}/users/trent_reznor/collection/folders",
    "curr_abbr": "USD",
    "email": "trent@example.com",
    "home_page": "https://www.nin.com/",
    "id": 1,
    "inventory_url": f"{BASE_URL}/users/trent_reznor/inventory",
    "location": "Los Angeles",
    "name": "Trent Reznor",
    "num_collection": 4,
    "num_for_sale": 6,
    "num_lists": 2,
    "num_pending": 10,
    "num_wantlist": 5,
    "profile": "Halo numbering enthusiast.",
    "rank": 30,
    "rating_avg": 4.62,
    "registered": "2011-08-30T14:21:45-07:00",
    "releases_contributed": 15,
    "releases_rated": 4,
    "resource_url": f"{BASE_URL}/users/trent_reznor",
    "seller_num_ratings": 20,
    "seller_rating": 99.5,
    "seller_rating_stars": 5.0,
    "uri": "https://www.discogs.com/user/trent_reznor",
    "username": "trent_reznor",
    "wantlist_url": f"{BASE_URL}/users/trent_reznor/wants",
}

LIST_DETAIL: dict[str, Any] = {
    "created_ts": "2011-10-20T22:35:33-07:00",
    "description": "Every Halo, in order.",
    "items": [
        {
            "comment": "Halo 8",
            "display_title": "Nine Inch Nails - The Downward Spiral",
            "id": 352665,
            "image_url": IMAGE_URL,
            "resource_url": f"{BASE_URL}/releases/352665",
            "type": "release",
            "uri": "https://www.discogs.com/release/352665",
        }
    ],
    "list_id": 1,
    "modified_ts": "2013-06-01T22:35:33-07:00",
    "name": "Industrial Essentials",
    "public": True,
    "resource_url": f"{BASE_URL}/lists/1",
    "url": "https://www.discogs.com/lists/1",
}

LIST_SUMMARY: dict[str, Any] = {
    "date_added": "2011-10-20T22:35:33-07:00",
    "date_changed": "2013-06-01T22:35:33-07:00",
    "description": "Every Halo, in order.",
    "id": 1,
    "name": "Industrial Essentials",
    "public": True,
    "resource_url": f"{BASE_URL}/lists/1",
    "uri": "https://www.discogs.com/lists/1",
}

EXPORT: dict[str, Any] = {
    "created_ts": "2018-07-01T12:00:00-07:00",
    "download_url": f"{BASE_URL}/inventory/export/599632/download",
    "filename": "trent_reznor-inventory-20180701-1200.csv",
    "finished_ts": "2018-07-01T12:00:30-07:00",
    "id": 599632,
    "status": "success",
    "url": f"{BASE_URL}/inventory/export/599632",
}

UPLOAD: dict[str, Any] = {
    "created_ts": "2019-03-27T18:44:00-07:00",
    "filename": "inventory.csv",
    "finished_ts": "2019-03-27T18:44:30-07:00",
    "id": 599632,
    "results": "CSV file contains 1 records.<p>Processed 1 records.",
    "status": "success",
    "type": "add",
}

# The submissions and contributions feeds return releases without the keys a
# release detail adds.
_SUBMISSION_ONLY_ABSENT = frozenset(
    {"extraartists", "identifiers", "lowest_price", "num_for_sale", "tracklist"}
)
SUBMITTED_RELEASE: dict[str, Any] = {
    k: v for k, v in RELEASE.items() if k not in _SUBMISSION_ONLY_ABSENT
}

# "Collection Items By Release" returns a slimmer basic_information than the
# by-folder feed, and spells out entity_type_name on each label.
COLLECTION_RELEASE_BASIC_INFORMATION: dict[str, Any] = {
    "artists": [ARTIST_CREDIT],
    "formats": [FORMAT],
    "id": 352665,
    "labels": [LABEL_CREDIT | {"entity_type_name": "Label"}],
    "resource_url": f"{BASE_URL}/releases/352665",
    "thumb": IMAGE_URL,
    "title": "The Downward Spiral",
    "year": 1994,
}

COLLECTION_RELEASE_ITEM: dict[str, Any] = {
    "basic_information": COLLECTION_RELEASE_BASIC_INFORMATION,
    "date_added": "2019-06-24T20:58:58-07:00",
    "folder_id": 1,
    "id": 352665,
    "instance_id": 45274429,
    "rating": 5,
}

# Suggested prices are keyed by condition name, so the body has no fixed schema.
PRICE_SUGGESTIONS: dict[str, Any] = {
    "Mint (M)": {"currency": "USD", "value": 39.99},
    "Near Mint (NM or M-)": {"currency": "USD", "value": 32.5},
    "Very Good Plus (VG+)": {"currency": "USD", "value": 24.99},
    "Very Good (VG)": {"currency": "USD", "value": 17.25},
    "Good Plus (G+)": {"currency": "USD", "value": 9.5},
    "Good (G)": {"currency": "USD", "value": 6.0},
    "Fair (F)": {"currency": "USD", "value": 4.0},
    "Poor (P)": {"currency": "USD", "value": 2.0},
}

# Home.md documents all four pagination URLs; a first page omits first/prev and
# a last page omits next/last, so both shapes have to survive the paginator.
PAGINATION_MIDDLE: dict[str, Any] = {
    "page": 2,
    "pages": 30,
    "items": 2255,
    "per_page": 75,
    "urls": {
        "first": f"{BASE_URL}/artists/3857/releases?page=1&per_page=75",
        "prev": f"{BASE_URL}/artists/3857/releases?page=1&per_page=75",
        "next": f"{BASE_URL}/artists/3857/releases?page=3&per_page=75",
        "last": f"{BASE_URL}/artists/3857/releases?page=30&per_page=75",
    },
}

PAGINATION_SINGLE: dict[str, Any] = {
    "page": 1,
    "pages": 1,
    "items": 1,
    "per_page": 50,
    "urls": {},
}


@dataclass(frozen=True)
class Example:
    """Identity of one ```json`` block in the reference.

    ``status`` is the HTTP status of the response the block illustrates, or
    ``"request"`` for a request body. ``ordinal`` disambiguates repeated blocks
    with the same status inside one section. ``path`` is a dotted path from the
    block's root to the object being mirrored (``""`` = the root itself).
    """

    doc: str
    section: str
    status: str = "200"
    ordinal: int = 0
    path: str = ""

    @property
    def id(self) -> str:
        return f"{self.doc}::{self.section}::{self.status}#{self.ordinal}"


@dataclass(frozen=True)
class DocumentedPayload:
    """A response body mirroring one or more examples in the reference.

    ``extra_keys`` holds dotted paths of keys the section documents in prose
    only, which are therefore absent from every example it claims.
    ``dynamic`` marks a body whose keys are data (suggested prices), where the
    model deliberately keeps everything in ``model_extra``.
    """

    model: type[BaseModel]
    payload: dict[str, Any]
    examples: tuple[Example, ...]
    extra_keys: frozenset[str] = field(default_factory=frozenset)
    dynamic: bool = False


@dataclass(frozen=True)
class DocumentedEnvelope:
    """A paginated body: the ``pagination`` object plus a keyed item list."""

    example: Example
    items_key: str
    item: str
    items_path: tuple[str, ...] | None = None


@dataclass(frozen=True)
class DocumentedError:
    """An error body, and the exception its status must raise."""

    example: Example
    status: int
    error: type[DiscogsAPIError]


def _ex(doc: str, section: str, status: str = "200", ordinal: int = 0, path: str = ""):
    return Example(doc, section, status, ordinal, path)


DOCUMENTED_PAYLOADS: dict[str, DocumentedPayload] = {
    "artist": DocumentedPayload(
        Artist,
        ARTIST,
        (_ex("Database.md", "Artist"),),
        # The reference's artist body omits "name"; every other artist
        # representation in the reference carries it.
        extra_keys=frozenset({"name"}),
    ),
    "artist_release": DocumentedPayload(
        ArtistRelease,
        ARTIST_RELEASE,
        (_ex("Database.md", "Artist Releases", path="releases"),),
    ),
    "collection_basic_information": DocumentedPayload(
        BasicInformation,
        COLLECTION_BASIC_INFORMATION,
        (
            _ex(
                "User Collection.md",
                "Collection Items By Folder",
                path="releases.basic_information",
            ),
        ),
    ),
    "collection_field": DocumentedPayload(
        CollectionField,
        COLLECTION_FIELD,
        (_ex("User Collection.md", "List Custom Fields", path="fields"),),
    ),
    "collection_folder": DocumentedPayload(
        CollectionFolder,
        COLLECTION_FOLDER,
        (
            _ex("User Collection.md", "Collection", path="folders"),
            _ex("User Collection.md", "Collection", status="201"),
            _ex("User Collection.md", "Collection Folder"),
            _ex("User Collection.md", "Collection Folder", ordinal=1),
        ),
    ),
    "collection_instance_created": DocumentedPayload(
        CollectionInstanceCreated,
        COLLECTION_INSTANCE_CREATED,
        (_ex("User Collection.md", "Add To Collection Folder", status="201"),),
    ),
    "collection_item": DocumentedPayload(
        CollectionItem,
        COLLECTION_ITEM,
        (_ex("User Collection.md", "Collection Items By Folder", path="releases"),),
    ),
    "collection_release_item": DocumentedPayload(
        CollectionItem,
        COLLECTION_RELEASE_ITEM,
        (_ex("User Collection.md", "Collection Items By Release", path="releases"),),
    ),
    "collection_value": DocumentedPayload(
        CollectionValue_,
        COLLECTION_VALUE,
        (_ex("User Collection.md", "Collection Value"),),
    ),
    "community_rating": DocumentedPayload(
        CommunityRating,
        COMMUNITY_RATING,
        (_ex("Database.md", "Community Release Rating"),),
    ),
    "export": DocumentedPayload(
        Export, EXPORT, (_ex("Inventory Export.md", "Get an export"),)
    ),
    "fee": DocumentedPayload(
        Fee,
        FEE,
        (_ex("Marketplace.md", "Fee"), _ex("Marketplace.md", "Fee with currency")),
    ),
    "identity": DocumentedPayload(
        Identity, IDENTITY, (_ex("User Identity.md", "Identity"),)
    ),
    "inventory_listing": DocumentedPayload(
        Listing,
        INVENTORY_LISTING,
        (_ex("Marketplace.md", "Inventory", path="listings"),),
    ),
    "label": DocumentedPayload(Label, LABEL, (_ex("Database.md", "Label"),)),
    "label_release": DocumentedPayload(
        LabelRelease,
        LABEL_RELEASE,
        (_ex("Database.md", "All Label Releases", path="releases"),),
    ),
    "list_detail": DocumentedPayload(
        List_, LIST_DETAIL, (_ex("User Lists.md", "List"),)
    ),
    "list_summary": DocumentedPayload(
        ListSummary, LIST_SUMMARY, (_ex("User Lists.md", "User Lists", path="lists"),)
    ),
    "listed_order": DocumentedPayload(
        Order, LISTED_ORDER, (_ex("Marketplace.md", "List Orders", path="orders"),)
    ),
    "listing": DocumentedPayload(
        Listing,
        LISTING,
        (_ex("Marketplace.md", "Listing"),),
        extra_keys=frozenset(
            {
                "external_id",
                "format_quantity",
                "in_cart",
                "location",
                "quantity",
                "weight",
            }
        ),
    ),
    "listing_created": DocumentedPayload(
        Listing, LISTING_CREATED, (_ex("Marketplace.md", "New Listing", status="201"),)
    ),
    "marketplace_release_stats": DocumentedPayload(
        MarketplaceReleaseStats,
        MARKETPLACE_RELEASE_STATS,
        (_ex("Marketplace.md", "Release Statistics"),),
    ),
    "master": DocumentedPayload(
        Master, MASTER, (_ex("Database.md", "Master Release"),)
    ),
    "master_version": DocumentedPayload(
        MasterVersion,
        MASTER_VERSION,
        (_ex("Database.md", "Master Release Versions", path="versions"),),
    ),
    "order": DocumentedPayload(
        Order,
        ORDER,
        (_ex("Marketplace.md", "Order"), _ex("Marketplace.md", "Order", ordinal=1)),
    ),
    "order_message": DocumentedPayload(
        OrderMessage,
        ORDER_MESSAGE,
        (
            _ex("Marketplace.md", "List Order Messages", path="messages"),
            _ex("Marketplace.md", "List Order Messages", status="201"),
        ),
    ),
    "price_suggestions": DocumentedPayload(
        PriceSuggestions,
        PRICE_SUGGESTIONS,
        (_ex("Marketplace.md", "Price Suggestions"),),
        dynamic=True,
    ),
    "release": DocumentedPayload(Release, RELEASE, (_ex("Database.md", "Release"),)),
    "release_stats": DocumentedPayload(
        ReleaseStats, RELEASE_STATS, (_ex("Database.md", "Release Stats"),)
    ),
    "search_result": DocumentedPayload(
        SearchResult, SEARCH_RESULT, (_ex("Database.md", "Search", path="results"),)
    ),
    "submitted_release": DocumentedPayload(
        Release,
        SUBMITTED_RELEASE,
        (
            _ex("User Identity.md", "User Submissions", path="submissions.releases"),
            _ex("User Identity.md", "User Contributions", path="contributions"),
        ),
    ),
    "upload": DocumentedPayload(
        Upload, UPLOAD, (_ex("Inventory Upload.md", "Get an upload"),)
    ),
    "user": DocumentedPayload(
        User,
        USER,
        (
            _ex("User Identity.md", "Profile"),
            _ex("User Identity.md", "Profile", ordinal=1),
        ),
    ),
    "user_release_rating": DocumentedPayload(
        UserReleaseRating,
        USER_RELEASE_RATING,
        (
            _ex("Database.md", "Release Rating By User"),
            _ex("Database.md", "Release Rating By User", ordinal=1),
        ),
    ),
    "added_want": DocumentedPayload(
        Want,
        ADDED_WANT,
        (
            _ex("User Wantlist.md", "Add To Wantlist", status="201"),
            _ex("User Wantlist.md", "Add To Wantlist"),
        ),
    ),
    "want": DocumentedPayload(
        Want, WANT, (_ex("User Wantlist.md", "Wantlist", path="wants"),)
    ),
    "wantlist_basic_information": DocumentedPayload(
        BasicInformation,
        WANTLIST_BASIC_INFORMATION,
        (_ex("User Wantlist.md", "Wantlist", path="wants.basic_information"),),
    ),
}

DOCUMENTED_ENVELOPES: dict[str, DocumentedEnvelope] = {
    "artist_releases": DocumentedEnvelope(
        _ex("Database.md", "Artist Releases"), "releases", "artist_release"
    ),
    "collection_items_by_folder": DocumentedEnvelope(
        _ex("User Collection.md", "Collection Items By Folder"),
        "releases",
        "collection_item",
    ),
    "collection_items_by_release": DocumentedEnvelope(
        _ex("User Collection.md", "Collection Items By Release"),
        "releases",
        "collection_release_item",
    ),
    "inventory": DocumentedEnvelope(
        _ex("Marketplace.md", "Inventory"), "listings", "inventory_listing"
    ),
    "label_releases": DocumentedEnvelope(
        _ex("Database.md", "All Label Releases"), "releases", "label_release"
    ),
    "master_versions": DocumentedEnvelope(
        _ex("Database.md", "Master Release Versions"), "versions", "master_version"
    ),
    "order_messages": DocumentedEnvelope(
        _ex("Marketplace.md", "List Order Messages"), "messages", "order_message"
    ),
    "orders": DocumentedEnvelope(
        _ex("Marketplace.md", "List Orders"), "orders", "listed_order"
    ),
    "recent_exports": DocumentedEnvelope(
        _ex("Inventory Export.md", "Get recent exports"), "items", "export"
    ),
    "recent_uploads": DocumentedEnvelope(
        _ex("Inventory Upload.md", "Get recent uploads"), "items", "upload"
    ),
    "search": DocumentedEnvelope(
        _ex("Database.md", "Search"), "results", "search_result"
    ),
    "user_contributions": DocumentedEnvelope(
        _ex("User Identity.md", "User Contributions"),
        "contributions",
        "submitted_release",
    ),
    "user_lists": DocumentedEnvelope(
        _ex("User Lists.md", "User Lists"), "lists", "list_summary"
    ),
    "user_submissions": DocumentedEnvelope(
        _ex("User Identity.md", "User Submissions"),
        "submissions",
        "submitted_release",
        items_path=("submissions", "releases"),
    ),
    "wantlist": DocumentedEnvelope(
        _ex("User Wantlist.md", "Wantlist"), "wants", "want"
    ),
}

DOCUMENTED_ERRORS: dict[str, DocumentedError] = {
    "artist_not_found": DocumentedError(
        _ex("Database.md", "Artist", status="404"), 404, NotFoundError
    ),
    "artist_releases_not_found": DocumentedError(
        _ex("Database.md", "Artist Releases", status="404"), 404, NotFoundError
    ),
    "collection_instance_forbidden": DocumentedError(
        _ex("User Collection.md", "Delete Instance From Folder", status="403"),
        403,
        ForbiddenError,
    ),
    "identity_unauthorized": DocumentedError(
        _ex("User Identity.md", "Identity", status="401"), 401, AuthenticationError
    ),
    "inventory_not_found": DocumentedError(
        _ex("Marketplace.md", "Inventory", status="404"), 404, NotFoundError
    ),
    "inventory_unprocessable": DocumentedError(
        _ex("Marketplace.md", "Inventory", status="422"), 422, ValidationError
    ),
    "label_not_found": DocumentedError(
        _ex("Database.md", "Label", status="404"), 404, NotFoundError
    ),
    "label_releases_not_found": DocumentedError(
        _ex("Database.md", "All Label Releases", status="404"), 404, NotFoundError
    ),
    "listing_not_found": DocumentedError(
        _ex("Marketplace.md", "Listing", status="404"), 404, NotFoundError
    ),
    "master_not_found": DocumentedError(
        _ex("Database.md", "Master Release", status="404"), 404, NotFoundError
    ),
    "master_versions_not_found": DocumentedError(
        _ex("Database.md", "Master Release Versions", status="404"),
        404,
        NotFoundError,
    ),
    "new_listing_forbidden": DocumentedError(
        _ex("Marketplace.md", "New Listing", status="403"), 403, ForbiddenError
    ),
    "order_bad_request": DocumentedError(
        _ex("Marketplace.md", "Order", status="400"), 400, DiscogsAPIError
    ),
    "order_forbidden": DocumentedError(
        _ex("Marketplace.md", "Order", status="403"), 403, ForbiddenError
    ),
    "order_messages_forbidden": DocumentedError(
        _ex("Marketplace.md", "List Order Messages", status="403"), 403, ForbiddenError
    ),
    "order_unauthorized": DocumentedError(
        _ex("Marketplace.md", "Order", status="401"), 401, AuthenticationError
    ),
    "profile_forbidden": DocumentedError(
        _ex("User Identity.md", "Profile", status="403"), 403, ForbiddenError
    ),
    "release_not_found": DocumentedError(
        _ex("Database.md", "Release", status="404"), 404, NotFoundError
    ),
    "search_server_error": DocumentedError(
        _ex("Database.md", "Search", status="500"), 500, DiscogsAPIError
    ),
    "search_server_error_repeat": DocumentedError(
        _ex("Database.md", "Search", status="500", ordinal=1), 500, DiscogsAPIError
    ),
}
