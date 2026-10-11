"""Test that API field names work as runtime attribute aliases on models.

Only the Python names are typed, so these tests read API names through
``getattr``: the type checker rejects them as plain attribute reads.
"""

from __future__ import annotations

import copy
import pickle
import types
import typing
from datetime import datetime

import pytest
from pydantic import AliasChoices, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

import discogs_sdk.models
from discogs_sdk.models._common import (
    ArtistCredit,
    Company,
    Format,
    Image,
    LabelCredit,
    SDKModel,
    Track,
    UserSummary,
)
from discogs_sdk.models.artist import Artist
from discogs_sdk.models.label import Label, LabelRelease
from discogs_sdk.models.list_ import List_
from discogs_sdk.models.marketplace import Listing, OrderMessage, OriginalPrice
from discogs_sdk.models.master import MasterVersion
from discogs_sdk.models.release import Release
from discogs_sdk.models.search import SearchResult
from discogs_sdk.models.user import User


class TestValidationAliasAccess:
    """API field names (validation_alias) resolve as attributes at runtime."""

    def test_image_uri150(self) -> None:
        image = Image.model_validate({"uri150": "https://example.com/thumb.jpg"})
        assert image.uri_150 == "https://example.com/thumb.jpg"
        assert getattr(image, "uri150") == "https://example.com/thumb.jpg"

    def test_artist_credit_anv(self) -> None:
        credit = ArtistCredit.model_validate({"anv": "DJ Shadow"})
        assert credit.name_variation == "DJ Shadow"
        assert getattr(credit, "anv") == "DJ Shadow"

    def test_track_extraartists(self) -> None:
        track = Track.model_validate({"extraartists": [{"name": "Someone"}]})
        assert track.extra_artists is not None
        assert getattr(track, "extraartists") is not None

    def test_format_qty(self) -> None:
        fmt = Format.model_validate({"qty": "2"})
        assert fmt.quantity == "2"
        assert getattr(fmt, "qty") == "2"

    def test_label_credit_catno(self) -> None:
        label = LabelCredit.model_validate({"catno": "ABC-123"})
        assert label.catalog_number == "ABC-123"
        assert getattr(label, "catno") == "ABC-123"

    def test_company_catno(self) -> None:
        company = Company.model_validate({"catno": "XYZ-456"})
        assert company.catalog_number == "XYZ-456"
        assert getattr(company, "catno") == "XYZ-456"

    def test_artist_namevariations(self) -> None:
        artist = Artist.model_validate(
            {"id": 1, "name": "Test", "namevariations": ["A", "B"]}
        )
        assert artist.name_variations == ["A", "B"]
        assert getattr(artist, "namevariations") == ["A", "B"]

    def test_label_sublabels(self) -> None:
        label = Label.model_validate(
            {"id": 1, "name": "Test", "sublabels": [{"id": 2, "name": "Sub"}]}
        )
        assert label.sub_labels is not None
        assert getattr(label, "sublabels") is not None

    def test_label_release_catno(self) -> None:
        lr = LabelRelease.model_validate({"id": 1, "title": "Test", "catno": "CAT-1"})
        assert lr.catalog_number == "CAT-1"
        assert getattr(lr, "catno") == "CAT-1"

    def test_master_version_catno(self) -> None:
        version = MasterVersion.model_validate(
            {"id": 1, "title": "The Downward Spiral", "catno": "HALO EIGHT"}
        )
        assert version.catalog_number == "HALO EIGHT"
        assert getattr(version, "catno") == "HALO EIGHT"

    def test_search_result_catno(self) -> None:
        result = SearchResult.model_validate(
            {"id": 1, "title": "Test", "catno": "SR-99"}
        )
        assert result.catalog_number == "SR-99"
        assert getattr(result, "catno") == "SR-99"

    def test_release_extraartists(self) -> None:
        release = Release.model_validate(
            {"id": 1, "title": "Test", "extraartists": [{"name": "Someone"}]}
        )
        assert release.extra_artists is not None
        assert getattr(release, "extraartists") is not None

    def test_original_price_curr_abbr(self) -> None:
        op = OriginalPrice.model_validate({"curr_abbr": "USD", "curr_id": 1})
        assert op.currency_code == "USD"
        assert getattr(op, "curr_abbr") == "USD"

    def test_user_curr_abbr(self) -> None:
        user = User.model_validate({"id": 1, "username": "test", "curr_abbr": "GBP"})
        assert user.currency_code == "GBP"
        assert getattr(user, "curr_abbr") == "GBP"


class TestAliasAccess:
    """An API name that is a Python keyword stays reachable through ``getattr``."""

    def test_order_message_from(self) -> None:
        msg = OrderMessage.model_validate({"from": {"username": "seller"}})
        assert msg.from_user is not None
        assert msg.from_user.username == "seller"
        # "from" is a keyword, so the API name is only reachable through getattr.
        assert getattr(msg, "from") == msg.from_user

    def test_order_message_by_alias_dump_keeps_python_name(self) -> None:
        msg = OrderMessage.model_validate(
            {"from": {"username": "seller"}, "message": "Shipped"}
        )
        dumped = msg.model_dump(by_alias=True)
        assert "from_user" in dumped
        assert "from" not in dumped
        assert dumped == msg.model_dump()
        assert OrderMessage.model_validate(dumped) == msg

    def test_order_message_python_name_populates_field(self) -> None:
        built = OrderMessage(from_user=UserSummary(username="seller"))
        validated = OrderMessage.model_validate({"from_user": {"username": "seller"}})
        for msg in (built, validated):
            assert msg.from_user is not None
            assert msg.from_user.username == "seller"
            assert msg.model_extra == {}


class TestAliasNoneValues:
    """Alias access should work when the field value is None."""

    def test_none_value_via_alias(self) -> None:
        image = Image()
        assert image.uri_150 is None
        assert getattr(image, "uri150") is None


class TestUnknownAttributeError:
    """Unknown attributes should still raise AttributeError."""

    def test_unknown_attr_raises(self) -> None:
        image = Image()
        with pytest.raises(AttributeError):
            getattr(image, "nonexistent")


class TestExtraFieldsStillWork:
    """Extra fields (from extra='allow') should still be accessible."""

    def test_extra_field_access(self) -> None:
        image = Image.model_validate(
            {"uri150": "https://example.com/thumb.jpg", "unknown_field": "value"}
        )
        assert getattr(image, "unknown_field") == "value"


class TestSubclassInheritsGetattr:
    """All SDKModel subclasses should inherit the __getattr__ behavior."""

    def test_custom_subclass(self) -> None:
        class MyModel(SDKModel):
            clean_name: str | None = Field(default=None, validation_alias="uglyName")

        obj = MyModel.model_validate({"uglyName": "hello"})
        assert obj.clean_name == "hello"
        assert getattr(obj, "uglyName") == "hello"


class TestAliasChoicesAccess:
    """A field accepting several API spellings exposes each as an attribute."""

    def test_detail_alias_is_readable(self) -> None:
        list_ = List_.model_validate({"list_id": 1, "name": "Halo"})
        assert list_.id == 1
        assert getattr(list_, "list_id") == 1

    def test_python_name_validates_and_reads_as_alias(self) -> None:
        list_ = List_.model_validate({"id": 1, "name": "Halo"})
        assert list_.id == 1
        assert getattr(list_, "list_id") == 1


class TestListingIdentifier:
    """``Listing.id`` reads only the detail spelling; ``listing_id`` is the ack's."""

    def test_detail_id_validates(self) -> None:
        assert Listing.model_validate({"id": 1}).id == 1

    def test_creation_acknowledgement_spelling_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            Listing.model_validate({"listing_id": 1})


def _sample(annotation: object) -> object:
    """Return input that validates as ``annotation``, never ``None``."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        options = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        return _sample(options[0])
    if origin is typing.Literal:
        return typing.get_args(annotation)[0]
    if origin is list:
        return [_sample(typing.get_args(annotation)[0])]
    if isinstance(annotation, type) and issubclass(annotation, SDKModel):
        return _required_payload(annotation)
    samples: dict[object, object] = {
        bool: True,
        datetime: "2005-01-03T23:17:26-08:00",
        float: 9.99,
        int: 3857,
        str: "Nine Inch Nails",
    }
    return samples[annotation]


def _required_payload(model: type[SDKModel]) -> dict[str, object]:
    return {
        name: _sample(field.annotation)
        for name, field in model.model_fields.items()
        if field.is_required()
    }


def _string_aliases(model: type[SDKModel], field_name: str) -> list[str]:
    alias = model.model_fields[field_name].validation_alias
    if isinstance(alias, AliasChoices):
        return [choice for choice in alias.choices if isinstance(choice, str)]
    return [alias] if isinstance(alias, str) else []


_EXPORTED_MODELS = [
    obj
    for obj in (
        getattr(discogs_sdk.models, name) for name in discogs_sdk.models.__all__
    )
    if isinstance(obj, type) and issubclass(obj, SDKModel)
]

_ALIASED_FIELDS = [
    pytest.param(model, field_name, id=f"{model.__name__}.{field_name}")
    for model in _EXPORTED_MODELS
    for field_name in model.model_fields
    if _string_aliases(model, field_name)
]


class TestEveryExportedAlias:
    """Every string alias of every exported model reads back its field's value."""

    @pytest.mark.parametrize(("model", "field_name"), _ALIASED_FIELDS)
    def test_alias_returns_field_value(
        self, model: type[SDKModel], field_name: str
    ) -> None:
        aliases = _string_aliases(model, field_name)
        field = model.model_fields[field_name]
        payload = _required_payload(model)
        payload.pop(field_name, None)
        payload[aliases[0]] = _sample(field.annotation)
        instance = model.model_validate(payload)
        value = instance.__dict__[field_name]
        assert value is not None
        for alias in aliases:
            assert getattr(instance, alias) is value


class TestAliasLookup:
    """Alias attributes resolve through a map built once per class."""

    def test_alias_map_is_built_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class Probe(SDKModel):
            clean_name: str | None = Field(default=None, validation_alias="uglyName")

        probe = Probe.model_validate({"uglyName": "Trent"})
        assert getattr(probe, "uglyName") == "Trent"
        # Later misses must not walk the fields again.
        monkeypatch.setattr(Probe, "__pydantic_fields__", {})
        assert getattr(probe, "uglyName") == "Trent"

    def test_subclass_does_not_resolve_redefined_parent_alias(self) -> None:
        class Parent(SDKModel):
            name: str | None = Field(default=None, validation_alias="parent_name")

        class Child(Parent):
            name: str | None = Field(default=None, validation_alias="child_name")

        # Resolve on the parent first, so its map exists before the child's.
        parent = Parent.model_validate({"parent_name": "Trent Reznor"})
        assert getattr(parent, "parent_name") == "Trent Reznor"

        child = Child.model_validate({"child_name": "Trent Reznor"})
        assert getattr(child, "child_name") == "Trent Reznor"
        with pytest.raises(AttributeError):
            getattr(child, "parent_name")

    def test_subclass_resolves_aliases_it_adds(self) -> None:
        class Parent(SDKModel):
            name: str | None = Field(default=None, validation_alias="parent_name")

        class Child(Parent):
            note: str | None = Field(default=None, validation_alias="child_note")

        assert getattr(Parent(name="Trent Reznor"), "parent_name") == "Trent Reznor"
        child = Child(name="Trent Reznor", note="Halo 8")
        assert getattr(child, "parent_name") == "Trent Reznor"
        assert getattr(child, "child_note") == "Halo 8"

    def test_first_declared_field_wins_a_shared_alias(self) -> None:
        class Shared(SDKModel):
            first: str | None = Field(default=None, validation_alias="shared")
            second: str | None = Field(
                default=None, validation_alias=AliasChoices("other", "shared")
            )

        model = Shared(first="Pretty Hate Machine", second="Broken")
        assert getattr(model, "shared") == "Pretty Hate Machine"
        assert getattr(model, "other") == "Broken"

    def test_extra_and_unknown_names_after_an_alias_read(self) -> None:
        image = Image.model_validate({"uri150": "x", "other": 1})
        assert getattr(image, "uri150") == "x"
        assert getattr(image, "other") == 1
        with pytest.raises(AttributeError):
            getattr(image, "nonexistent")

    def test_copies_keep_alias_and_extra_access(self) -> None:
        image = Image.model_validate({"uri150": "thumb.jpg", "other": "x"})
        for copied in (copy.deepcopy(image), pickle.loads(pickle.dumps(image))):
            assert copied == image
            assert getattr(copied, "uri150") == "thumb.jpg"
            assert getattr(copied, "other") == "x"
            assert copied.raw == image.raw


class TestCanonicalNameValidation:
    """Canonical field names must populate the declared field, not land in extras."""

    def test_constructor_uses_canonical_name(self) -> None:
        image = Image(uri_150="https://example.com/thumb.jpg")
        assert image.uri_150 == "https://example.com/thumb.jpg"
        assert "uri_150" not in (image.model_extra or {})

    def test_alias_wins_when_both_names_are_supplied(self) -> None:
        image = Image.model_validate(
            {"uri150": "from-alias", "uri_150": "from-canonical"}
        )
        assert image.uri_150 == "from-alias"
        assert image.model_extra == {}
        assert image.model_dump()["uri_150"] == "from-alias"
        assert Image.model_validate(image.model_dump()) == image
        assert Image.model_validate_json(image.model_dump_json()) == image
        from_json = Image.model_validate_json(
            '{"uri150": "from-alias", "uri_150": "from-canonical"}'
        )
        assert from_json == image

    def test_alias_wins_on_a_model_with_several_fields(self) -> None:
        credit = LabelCredit.model_validate(
            {
                "id": 647,
                "name": "Nothing Records",
                "catno": "ALIAS",
                "catalog_number": "NAME",
            }
        )
        assert credit.catalog_number == "ALIAS"
        assert credit.model_extra == {}
        assert credit.model_dump()["catalog_number"] == "ALIAS"
        assert LabelCredit.model_validate(credit.model_dump()) == credit
        assert LabelCredit.model_validate_json(credit.model_dump_json()) == credit

    def test_alias_wins_in_a_nested_model(self) -> None:
        release = Release.model_validate(
            {
                "id": 352665,
                "title": "The Downward Spiral",
                "labels": [
                    {
                        "id": 647,
                        "name": "Nothing Records",
                        "catno": "ALIAS",
                        "catalog_number": "NAME",
                    }
                ],
            }
        )
        assert release.labels is not None
        assert release.labels[0].catalog_number == "ALIAS"
        assert release.labels[0].model_extra == {}
        assert release.model_dump()["labels"][0]["catalog_number"] == "ALIAS"
        assert Release.model_validate(release.model_dump()) == release
        assert Release.model_validate_json(release.model_dump_json()) == release

    def test_unknown_keys_stay_in_extras(self) -> None:
        image = Image.model_validate({"uri150": "x", "future_field": 1})
        assert image.model_extra == {"future_field": 1}

    def test_lone_python_name_survives_when_names_are_not_accepted(self) -> None:
        class AliasOnlyImage(Image):
            model_config = ConfigDict(validate_by_name=False)

        image = AliasOnlyImage.model_validate({"uri_150": "kept"})
        assert image.uri_150 is None
        assert image.model_extra == {"uri_150": "kept"}

    def test_canonical_name_is_validated_like_the_alias(self) -> None:
        with pytest.raises(PydanticValidationError):
            Image.model_validate({"uri_150": 42})
        with pytest.raises(PydanticValidationError):
            Image.model_validate({"uri150": 42})


class TestRoundTrip:
    """model_dump() emits canonical names, so re-validating must preserve values."""

    def test_scalar_round_trip(self) -> None:
        image = Image.model_validate(
            {"uri150": "https://example.com/thumb.jpg", "width": 150}
        )
        assert (
            Image.model_validate(image.model_dump()).uri_150
            == "https://example.com/thumb.jpg"
        )

    def test_json_round_trip(self) -> None:
        image = Image.model_validate({"uri150": "https://example.com/thumb.jpg"})
        assert (
            Image.model_validate_json(image.model_dump_json()).uri_150
            == "https://example.com/thumb.jpg"
        )

    def test_nested_list_round_trip(self) -> None:
        release = Release.model_validate(
            {
                "id": 352665,
                "title": "The Downward Spiral",
                "extraartists": [
                    {
                        "id": 3857,
                        "name": "Nine Inch Nails",
                        "anv": "NIN",
                        "role": "Producer",
                    }
                ],
            }
        )
        restored = Release.model_validate(release.model_dump())
        assert restored.extra_artists is not None
        assert restored.extra_artists[0].name_variation == "NIN"
        assert getattr(restored.extra_artists[0], "anv") == "NIN"
