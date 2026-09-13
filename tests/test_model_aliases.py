"""Test that API field names work as attribute aliases on models."""

from __future__ import annotations

import pytest
from pydantic import Field
from pydantic import ValidationError as PydanticValidationError

from discogs_sdk.models._common import (
    ArtistCredit,
    Company,
    Format,
    Image,
    LabelCredit,
    SDKModel,
    Track,
)
from discogs_sdk.models.artist import Artist
from discogs_sdk.models.label import Label, LabelRelease
from discogs_sdk.models.marketplace import Listing, OrderMessage, OriginalPrice
from discogs_sdk.models.release import Release
from discogs_sdk.models.search import SearchResult
from discogs_sdk.models.user import User


class TestValidationAliasAccess:
    """API field names (validation_alias) should be accessible as attributes."""

    def test_image_uri150(self) -> None:
        image = Image.model_validate({"uri150": "https://example.com/thumb.jpg"})
        assert image.uri_150 == "https://example.com/thumb.jpg"
        assert image.uri150 == "https://example.com/thumb.jpg"

    def test_artist_credit_anv(self) -> None:
        credit = ArtistCredit.model_validate({"anv": "DJ Shadow"})
        assert credit.name_variation == "DJ Shadow"
        assert credit.anv == "DJ Shadow"

    def test_track_extraartists(self) -> None:
        track = Track.model_validate({"extraartists": [{"name": "Someone"}]})
        assert track.extra_artists is not None
        assert track.extraartists is not None

    def test_format_qty(self) -> None:
        fmt = Format.model_validate({"qty": "2"})
        assert fmt.quantity == "2"
        assert fmt.qty == "2"

    def test_label_credit_catno(self) -> None:
        label = LabelCredit.model_validate({"catno": "ABC-123"})
        assert label.catalog_number == "ABC-123"
        assert label.catno == "ABC-123"

    def test_company_catno(self) -> None:
        company = Company.model_validate({"catno": "XYZ-456"})
        assert company.catalog_number == "XYZ-456"
        assert company.catno == "XYZ-456"

    def test_artist_namevariations(self) -> None:
        artist = Artist.model_validate({"id": 1, "name": "Test", "namevariations": ["A", "B"]})
        assert artist.name_variations == ["A", "B"]
        assert artist.namevariations == ["A", "B"]

    def test_label_sublabels(self) -> None:
        label = Label.model_validate({"id": 1, "name": "Test", "sublabels": [{"id": 2, "name": "Sub"}]})
        assert label.sub_labels is not None
        assert label.sublabels is not None

    def test_label_release_catno(self) -> None:
        lr = LabelRelease.model_validate({"id": 1, "title": "Test", "catno": "CAT-1"})
        assert lr.catalog_number == "CAT-1"
        assert lr.catno == "CAT-1"

    def test_search_result_catno(self) -> None:
        result = SearchResult.model_validate({"id": 1, "title": "Test", "catno": "SR-99"})
        assert result.catalog_number == "SR-99"
        assert result.catno == "SR-99"

    def test_release_extraartists(self) -> None:
        release = Release.model_validate({"id": 1, "title": "Test", "extraartists": [{"name": "Someone"}]})
        assert release.extra_artists is not None
        assert release.extraartists is not None

    def test_original_price_curr_abbr(self) -> None:
        op = OriginalPrice.model_validate({"curr_abbr": "USD", "curr_id": 1})
        assert op.currency_code == "USD"
        assert op.curr_abbr == "USD"

    def test_user_curr_abbr(self) -> None:
        user = User.model_validate({"id": 1, "username": "test", "curr_abbr": "GBP"})
        assert user.currency_code == "GBP"
        assert user.curr_abbr == "GBP"


class TestAliasAccess:
    """Fields using alias= (not validation_alias=) should also work."""

    def test_order_message_from(self) -> None:
        msg = OrderMessage.model_validate({"from": {"username": "seller"}})
        assert msg.from_user is not None
        assert msg.from_user.username == "seller"
        # Access via the alias="from" name
        assert getattr(msg, "from") is not None
        assert getattr(msg, "from").username == "seller"


class TestAliasNoneValues:
    """Alias access should work when the field value is None."""

    def test_none_value_via_alias(self) -> None:
        image = Image()
        assert image.uri_150 is None
        assert image.uri150 is None


class TestUnknownAttributeError:
    """Unknown attributes should still raise AttributeError."""

    def test_unknown_attr_raises(self) -> None:
        image = Image()
        with pytest.raises(AttributeError):
            image.nonexistent  # noqa: B018


class TestExtraFieldsStillWork:
    """Extra fields (from extra='allow') should still be accessible."""

    def test_extra_field_access(self) -> None:
        image = Image.model_validate({"uri150": "https://example.com/thumb.jpg", "unknown_field": "value"})
        assert image.unknown_field == "value"


class TestSubclassInheritsGetattr:
    """All SDKModel subclasses should inherit the __getattr__ behavior."""

    def test_custom_subclass(self) -> None:
        class MyModel(SDKModel):
            clean_name: str | None = Field(default=None, validation_alias="uglyName")

        obj = MyModel.model_validate({"uglyName": "hello"})
        assert obj.clean_name == "hello"
        assert obj.uglyName == "hello"


class TestAliasChoicesAccess:
    """A field accepting several API spellings exposes each as an attribute."""

    def test_creation_alias_is_readable(self) -> None:
        listing = Listing.model_validate({"listing_id": 41578241})
        assert listing.id == 41578241
        assert listing.listing_id == 41578241

    def test_detail_alias_is_readable(self) -> None:
        listing = Listing.model_validate({"id": 123})
        assert listing.listing_id == 123


class TestCanonicalNameValidation:
    """Canonical field names must populate the declared field, not land in extras."""

    def test_constructor_uses_canonical_name(self) -> None:
        image = Image(uri_150="https://example.com/thumb.jpg")
        assert image.uri_150 == "https://example.com/thumb.jpg"
        assert "uri_150" not in (image.model_extra or {})

    def test_alias_wins_when_both_names_are_supplied(self) -> None:
        image = Image.model_validate({"uri150": "from-alias", "uri_150": "from-canonical"})
        assert image.uri_150 == "from-alias"

    def test_canonical_name_is_validated_like_the_alias(self) -> None:
        with pytest.raises(PydanticValidationError):
            Image.model_validate({"uri_150": 42})
        with pytest.raises(PydanticValidationError):
            Image.model_validate({"uri150": 42})


class TestRoundTrip:
    """model_dump() emits canonical names, so re-validating must preserve values."""

    def test_scalar_round_trip(self) -> None:
        image = Image.model_validate({"uri150": "https://example.com/thumb.jpg", "width": 150})
        assert Image.model_validate(image.model_dump()).uri_150 == "https://example.com/thumb.jpg"

    def test_json_round_trip(self) -> None:
        image = Image.model_validate({"uri150": "https://example.com/thumb.jpg"})
        assert Image.model_validate_json(image.model_dump_json()).uri_150 == "https://example.com/thumb.jpg"

    def test_nested_list_round_trip(self) -> None:
        release = Release.model_validate(
            {
                "id": 352665,
                "title": "The Downward Spiral",
                "extraartists": [{"id": 3857, "name": "Nine Inch Nails", "anv": "NIN", "role": "Producer"}],
            }
        )
        restored = Release.model_validate(release.model_dump())
        assert restored.extra_artists is not None
        assert restored.extra_artists[0].name_variation == "NIN"
        assert restored.extra_artists[0].anv == "NIN"
