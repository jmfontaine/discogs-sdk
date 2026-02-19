from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class SDKModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


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
    extra_artists: list[ArtistCredit] | None = Field(default=None, validation_alias="extraartists")
    position: str | None = None
    sub_tracks: list[Track] | None = None
    title: str | None = None
    type_: str | None = None


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
