from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from discogs_sdk._async._lazy import AsyncLazyResource
from discogs_sdk._async._paginator import AsyncPage
from discogs_sdk._async._resource import AsyncAPIResource
from discogs_sdk._async.resources.collection import Collection
from discogs_sdk._async.resources.lists import UserLists
from discogs_sdk._async.resources.wantlist import Wantlist
from discogs_sdk.models.artist import Artist
from discogs_sdk.models.label import Label
from discogs_sdk.models.marketplace import Listing
from discogs_sdk.models.release import Release
from discogs_sdk.models.user import Identity, User

if TYPE_CHECKING:
    from discogs_sdk._async._client import AsyncDiscogs


class UserUpdate(AsyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    async def __call__(
        self,
        *,
        name: str | None = None,
        home_page: str | None = None,
        location: str | None = None,
        profile: str | None = None,
        curr_abbr: str | None = None,
    ) -> User:
        """Edit the user's profile.

        Only the fields you pass are sent, so omitting one leaves it untouched.
        Passing an empty string clears that field.
        """
        body = {
            k: v
            for k, v in {
                "name": name,
                "home_page": home_page,
                "location": location,
                "profile": profile,
                "curr_abbr": curr_abbr,
            }.items()
            if v is not None
        }
        response = await self._post(f"/users/{self._username}", json=body)
        return self._parse_response(response, User)


class UserSubmissionArtists(AsyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[Artist]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            items_key="submissions",
            items_path=["submissions", "artists"],
            model_cls=Artist,
            params=params,
            path=f"/users/{self._username}/submissions",
        )


class UserSubmissionLabels(AsyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[Label]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
            client=self._client,
            items_key="submissions",
            items_path=["submissions", "labels"],
            model_cls=Label,
            params=params,
            path=f"/users/{self._username}/submissions",
        )


class UserSubmissions(AsyncAPIResource):
    def __init__(self, client, username: str) -> None:
        super().__init__(client)
        self._username = username

    def list(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
    ) -> AsyncPage[Release]:
        params = {k: v for k, v in {"page": page, "per_page": per_page}.items() if v}
        return AsyncPage(
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


class UserContributions(AsyncAPIResource):
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
    ) -> AsyncPage[Release]:
        params = {
            k: v for k, v in {"sort": sort, "sort_order": sort_order, "page": page, "per_page": per_page}.items() if v
        }
        return AsyncPage(
            client=self._client,
            items_key="contributions",
            model_cls=Release,
            params=params,
            path=f"/users/{self._username}/contributions",
        )


class UserInventory(AsyncAPIResource):
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
    ) -> AsyncPage[Listing]:
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
        return AsyncPage(
            client=self._client,
            items_key="listings",
            model_cls=Listing,
            params=params,
            path=f"/users/{self._username}/inventory",
        )


class UserNamespace:
    """Convenience namespace for the authenticated user (discogs.user.identity())."""

    def __init__(self, client: AsyncDiscogs) -> None:
        self._client = client

    async def identity(self) -> Identity:
        response = await self._client._send("GET", self._client._build_url("/oauth/identity"))
        return Identity.model_validate(response.json())


class UserProxy(AsyncLazyResource[User]):
    """Lazy ``User`` with its typed sub-resources."""

    _username: str

    def __init__(self, client: AsyncDiscogs, username: str) -> None:
        super().__init__(client, f"/users/{username}", User)
        self._username = username

    @cached_property
    def collection(self) -> Collection:
        return Collection(self._client, self._username)

    @cached_property
    def contributions(self) -> UserContributions:
        return UserContributions(self._client, self._username)

    @cached_property
    def inventory(self) -> UserInventory:
        return UserInventory(self._client, self._username)

    @cached_property
    def lists(self) -> UserLists:
        return UserLists(self._client, self._username)

    @cached_property
    def submissions(self) -> UserSubmissions:
        return UserSubmissions(self._client, self._username)

    @cached_property
    def update(self) -> UserUpdate:
        return UserUpdate(self._client, self._username)

    @cached_property
    def wantlist(self) -> Wantlist:
        return Wantlist(self._client, self._username)


class Users(AsyncAPIResource):
    def get(self, username: str) -> UserProxy:
        return UserProxy(self._client, username)
