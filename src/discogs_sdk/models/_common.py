from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    PrivateAttr,
    model_validator,
)

Condition = Literal[
    "Mint (M)",
    "Near Mint (NM or M-)",
    "Very Good Plus (VG+)",
    "Very Good (VG)",
    "Good Plus (G+)",
    "Good (G)",
    "Fair (F)",
    "Poor (P)",
]

SleeveCondition = Literal[
    "Mint (M)",
    "Near Mint (NM or M-)",
    "Very Good Plus (VG+)",
    "Very Good (VG)",
    "Good Plus (G+)",
    "Good (G)",
    "Fair (F)",
    "Poor (P)",
    "Not Graded",
    "Generic",
    "No Cover",
]

CurrencyCode = Literal[
    "USD",
    "GBP",
    "EUR",
    "CAD",
    "AUD",
    "JPY",
    "CHF",
    "MXN",
    "BRL",
    "NZD",
    "SEK",
    "ZAR",
]


class _RawPayload:
    """Holder for :attr:`SDKModel.raw` that never affects model equality.

    Pydantic compares private attributes in ``__eq__``. The payload records where
    a model came from, not what it holds, so a model must still equal its own
    ``model_validate(model.model_dump())`` round-trip, whose input differs.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        self.data = data

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _RawPayload)

    __hash__ = None  # type: ignore[assignment]


# Class attribute holding the alias map of one SDKModel subclass. It is read from
# the class's own ``__dict__``, never through inheritance, so a subclass that adds
# or redefines fields builds its own map instead of reusing its parent's.
_ALIAS_FIELDS = "__sdk_alias_fields__"


def _build_alias_fields(cls: type[BaseModel]) -> dict[str, str]:
    """Map each string validation alias of ``cls`` to the field it fills.

    Pydantic copies ``Field(alias=...)`` into ``validation_alias``, so this covers
    plain aliases too. When fields share an alias, the first declared one wins.
    """
    alias_fields: dict[str, str] = {}
    for field_name, field_info in cls.model_fields.items():
        validation_alias = field_info.validation_alias
        if isinstance(validation_alias, AliasChoices):
            aliases = [
                choice for choice in validation_alias.choices if isinstance(choice, str)
            ]
        elif isinstance(validation_alias, str):
            aliases = [validation_alias]
        else:
            continue
        for alias in aliases:
            alias_fields.setdefault(alias, field_name)
    # Threads racing on the first miss build equal maps; either one may be kept.
    setattr(cls, _ALIAS_FIELDS, alias_fields)
    return alias_fields


class SDKModel(BaseModel):
    # Accept both the canonical Python field name and the API alias, so a model
    # survives ``model_validate(model_dump())`` and can be built from keyword
    # arguments. Aliases keep priority when an input supplies both spellings.
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="allow",
        validate_by_alias=True,
        validate_by_name=True,
    )

    _raw: _RawPayload = PrivateAttr(default_factory=lambda: _RawPayload({}))

    @property
    def raw(self) -> Mapping[str, Any]:
        """The mapping this model was validated from, as the API sent it.

        Fields normalize what Discogs sends: renamed keys (``catno`` becomes
        ``catalog_number``) and parsed timestamps (``"2005-01-03T23:17:26-08:00"``
        becomes a ``datetime``). ``raw`` keeps the original, so
        ``release.raw["date_added"]`` is the string exactly as received. Nested
        models expose their own part of the payload.

        It is the decoded response itself, not a copy: changing it changes what
        later reads see, and it is not a frozen record of the response. Holding
        a model keeps the whole payload in memory. A model built from keyword
        arguments or from ``model_validate(model.model_dump())`` reports that
        input instead; one from ``model_construct()`` reports ``{}``. ``raw`` is
        left out of ``model_dump()`` and of equality.
        """
        return self._raw.data

    @model_validator(mode="wrap")
    @classmethod
    def _keep_raw(
        cls, data: Any, handler: ModelWrapValidatorHandler[SDKModel]
    ) -> SDKModel:
        # A wrap validator makes pydantic decode JSON input to Python before
        # validating it. The SDK always validates ``response.json()``, so that
        # decoding happens anyway.
        model = handler(data)
        # A model instance passed in is returned as is and keeps its own payload.
        if isinstance(data, Mapping):
            model._raw = _RawPayload(data)
        return model

    @model_validator(mode="after")
    def _drop_losing_field_names(self) -> SDKModel:
        # When an input supplies both spellings, pydantic validates the alias into
        # the field and keeps the Python-name key as an extra, which would then
        # override the field in ``model_dump()``. With names accepted, that is the
        # only way a declared field name reaches the extras, so drop it. A caller
        # passing ``by_name=False`` to one validation is not covered: its lone
        # Python-name key is dropped too.
        extra = self.__pydantic_extra__
        if extra and type(self).model_config.get("validate_by_name"):
            for name in extra.keys() & type(self).model_fields.keys():
                del extra[name]
        return self

    if not TYPE_CHECKING:
        # Resolves API-name aliases (``release.extraartists``) at runtime only.
        # Like pydantic's own ``BaseModel.__getattr__``, it stays hidden from type
        # checkers so that a misspelled attribute is a static error, not ``Any``.
        def __getattr__(self, name: str) -> Any:
            cls = type(self)
            alias_fields = cls.__dict__.get(_ALIAS_FIELDS)
            if alias_fields is None:
                alias_fields = _build_alias_fields(cls)
            field_name = alias_fields.get(name)
            if field_name is not None:
                return self.__dict__.get(field_name)
            return super().__getattr__(name)


class Price(SDKModel):
    currency: CurrencyCode | str
    value: float


class Image(SDKModel):
    height: int | None = None
    resource_url: str | None = None
    type: str | None = None
    uri_150: str | None = Field(default=None, validation_alias="uri150")
    uri: str | None = None
    width: int | None = None


class Video(SDKModel):
    description: str | None = None
    duration: int | None = None
    embed: bool | None = None
    title: str | None = None
    uri: str | None = None


class ArtistCredit(SDKModel):
    id: int | None = None
    join: str | None = None
    name_variation: str | None = Field(default=None, validation_alias="anv")
    name: str | None = None
    resource_url: str | None = None
    role: str | None = None
    tracks: str | None = None


class Track(SDKModel):
    artists: list[ArtistCredit] | None = None
    duration: str | None = None
    extra_artists: list[ArtistCredit] | None = Field(
        default=None, validation_alias="extraartists"
    )
    position: str | None = None
    sub_tracks: list[Track] | None = None
    title: str | None = None
    type: str | None = Field(default=None, validation_alias="type_")


class Format(SDKModel):
    descriptions: list[str] | None = None
    name: str | None = None
    quantity: str | None = Field(default=None, validation_alias="qty")
    text: str | None = None


class LabelCredit(SDKModel):
    id: int | None = None
    catalog_number: str | None = Field(default=None, validation_alias="catno")
    entity_type_name: str | None = None
    entity_type: str | None = None
    name: str | None = None
    resource_url: str | None = None


class Company(SDKModel):
    id: int | None = None
    catalog_number: str | None = Field(default=None, validation_alias="catno")
    entity_type_name: str | None = None
    entity_type: str | None = None
    name: str | None = None
    resource_url: str | None = None


class Identifier(SDKModel):
    description: str | None = None
    type: str | None = None
    value: str | None = None


class UserSummary(SDKModel):
    id: int | None = None
    avatar_url: str | None = None
    resource_url: str | None = None
    username: str | None = None


class CommunityRatingValue(SDKModel):
    average: float | None = None
    count: int | None = None


class Community(SDKModel):
    contributors: list[UserSummary] | None = None
    data_quality: str | None = None
    have: int | None = None
    rating: CommunityRatingValue | None = None
    status: str | None = None
    submitter: UserSummary | None = None
    want: int | None = None


class BasicInformation(SDKModel):
    id: int
    artists: list[ArtistCredit] | None = None
    cover_image: str | None = None
    formats: list[Format] | None = None
    genres: list[str] | None = None
    labels: list[LabelCredit] | None = None
    master_id: int | None = None
    master_url: str | None = None
    resource_url: str | None = None
    styles: list[str] | None = None
    thumb: str | None = None
    title: str | None = None
    year: int | None = None


class Member(SDKModel):
    id: int | None = None
    active: bool | None = None
    name: str | None = None
    resource_url: str | None = None


class SubLabel(SDKModel):
    id: int | None = None
    name: str | None = None
    resource_url: str | None = None
