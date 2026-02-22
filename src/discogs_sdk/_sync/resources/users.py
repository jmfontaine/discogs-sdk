# This file is auto-generated from the async version.
# Do not edit directly — edit the corresponding file in _async/ instead.

from __future__ import annotations
from typing import TYPE_CHECKING
from discogs_sdk._sync._lazy import LazyResource
from discogs_sdk._sync._paginator import SyncPage
from discogs_sdk._sync._resource import SyncAPIResource
from discogs_sdk.models.artist import Artist
from discogs_sdk.models.label import Label
from discogs_sdk.models.marketplace import Listing
from discogs_sdk.models.release import Release
from discogs_sdk.models.user import Identity, User

if TYPE_CHECKING:
    from discogs_sdk._sync._client import Discogs


class UserUpdate(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def __call__(
        self,
        *,
        name: str | None = None,
        home_page: str | None = None,
        location: str | None = None,
        curr_abbr: str | None = None,
    ) -> User:
        body = {
            k: v
            for k, v in {"name": name, "home_page": home_page, "location": location, "curr_abbr": curr_abbr}.items()
            if v is not None
        }
        response = self._post(f"/users/{self._username}", json=body)
        return self._parse_response(response, User)


class UserSubmissionArtists(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(self, *, page: int | None = None, per_page: int | None = None) -> SyncPage[Artist]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client,
            items_key="submissions",
            items_path=["submissions", "artists"],
            model_cls=Artist,
            params=params,
            path=f"/users/{self._username}/submissions",
        )


class UserSubmissionLabels(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(self, *, page: int | None = None, per_page: int | None = None) -> SyncPage[Label]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client,
            items_key="submissions",
            items_path=["submissions", "labels"],
            model_cls=Label,
            params=params,
            path=f"/users/{self._username}/submissions",
        )


class UserSubmissions(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(self, *, page: int | None = None, per_page: int | None = None) -> SyncPage[Release]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return SyncPage(
            client=self._client,
            items_key="submissions",
            items_path=["submissions", "releases"],
            model_cls=Release,
            params=params,
            path=f"/users/{self._username}/submissions",
        )

    @property
    def artists(self) -> UserSubmissionArtists:
        return UserSubmissionArtists(self._client, self._username)

    @property
    def labels(self) -> UserSubmissionLabels:
        return UserSubmissionLabels(self._client, self._username)


class UserContributions(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self,
        *,
        sort: str | None = None,
        sort_order: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
    ) -> SyncPage[Release]:
        params = {
            k: v for k, v in {"sort": sort, "sort_order": sort_order, "page": page, "per_page": per_page}.items() if v
        }
        return SyncPage(
            client=self._client,
            items_key="contributions",
            model_cls=Release,
            params=params,
            path=f"/users/{self._username}/contributions",
        )


class UserInventory(SyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self,
        *,
        sort: str | None = None,
        sort_order: str | None = None,
        status: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
    ) -> SyncPage[Listing]:
        params = {
            k: v
            for k, v in {
                "sort": sort,
                "sort_order": sort_order,
                "status": status,
                "page": page,
                "per_page": per_page,
            }.items()
            if v
        }
        return SyncPage(
            client=self._client,
            items_key="listings",
            model_cls=Listing,
            params=params,
            path=f"/users/{self._username}/inventory",
        )


class UserNamespace:
    """Convenience namespace for the authenticated user (discogs.user.identity())."""

    def __init__(self, client: Discogs) -> None:
        self._client = client

    def identity(self) -> Identity:
        response = self._client._send("GET", self._client._build_url("/oauth/identity"))
        body = response.json()
        self._client._maybe_raise(response.status_code, body, retry_after=response.headers.get("Retry-After"))
        return Identity.model_validate(body)


class Users(SyncAPIResource):
    def get(self, username: str) -> LazyResource:
        from discogs_sdk._sync.resources.collection import Collection
        from discogs_sdk._sync.resources.lists import UserLists
        from discogs_sdk._sync.resources.wantlist import Wantlist

        return LazyResource(
            client=self._client,
            path=f"/users/{username}",
            model_cls=User,
            sub_resources={
                "collection": lambda: Collection(self._client, username),
                "contributions": lambda: UserContributions(self._client, username),
                "inventory": lambda: UserInventory(self._client, username),
                "lists": lambda: UserLists(self._client, username),
                "submissions": lambda: UserSubmissions(self._client, username),
                "update": lambda: UserUpdate(self._client, username),
                "wantlist": lambda: Wantlist(self._client, username),
            },
        )
