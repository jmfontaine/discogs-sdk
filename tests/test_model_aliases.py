"""Test that API field names work as attribute aliases on models."""

from __future__ import annotations

import pytest
from pydantic import Field

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
from discogs_sdk.models.marketplace import OrderMessage, OriginalPrice
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
