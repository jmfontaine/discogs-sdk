"""Tests for the route extractor in ``scripts/generate_endpoints.py``.

The real SDK is covered by ``just endpoints-check``, which fails when
``docs/endpoints.md`` drifts from the sources. These tests feed the extractor small
sources shaped like the patterns that once broke it.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_endpoints.py"


def _load_generator() -> ModuleType:
    # `scripts/` is not a package, so load the file directly.
    spec = importlib.util.spec_from_file_location("generate_endpoints", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their own module through sys.modules while decorating.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen = _load_generator()

CLIENT = """
from functools import cached_property

class AsyncDiscogs:
    @cached_property
    def things(self) -> Things:
        return Things(self)

    def cache_only(self) -> None: ...
    def clear_cache(self) -> None: ...
    def close(self) -> None: ...
    def no_cache(self) -> None: ...
"""

RESOURCE_BASE = """
class AsyncAPIResource:
    def _parse_response(self, response, model_cls):
        return model_cls.model_validate(response.json())
"""

RESOURCE_HEAD = """
class Things(AsyncAPIResource):
"""


def _sources(body: str, extra: str = "", client: str = "") -> dict[str, str]:
    return {
        "_client": textwrap.dedent(CLIENT)
        + textwrap.indent(textwrap.dedent(client), "    "),
        "_resource": textwrap.dedent(RESOURCE_BASE),
        "resources/things": textwrap.dedent(RESOURCE_HEAD)
        + textwrap.indent(textwrap.dedent(body), "    ")
        + textwrap.dedent(extra),
    }


def _rows(body: str, extra: str = "", client: str = "") -> list[tuple[str, str, str]]:
    endpoint_map = gen.build_map(_sources(body, extra, client))
    return [(r.verb, r.route, r.call) for r in endpoint_map.operations]


def _full(
    body: str, extra: str = "", client: str = ""
) -> list[tuple[str, str, str, str, bool]]:
    endpoint_map = gen.build_map(_sources(body, extra, client))
    return [
        (r.verb, r.route, r.call, r.returns, r.paginated)
        for r in endpoint_map.operations
    ]


def test_reassigned_path_yields_both_variants() -> None:
    rows = _rows(
        """
        def get(self, *, price: float, currency: str | None = None) -> FeeProxy:
            path = f"/marketplace/fee/{path_segment(price)}"
            if currency:
                path = f"{path}/{path_segment(currency)}"
            return FeeProxy(self._client, path, Fee)
        """,
        """
class FeeProxy(AsyncLazyResource[Fee]):
    pass
        """,
    )
    assert rows == [
        ("GET", "/marketplace/fee/{price}", "client.things.get(price=..., ...)"),
        (
            "GET",
            "/marketplace/fee/{price}/{currency}",
            "client.things.get(price=..., currency=...)",
        ),
    ]


def test_path_composed_from_local_variables_is_one_route() -> None:
    endpoint_map = gen.build_map(
        _sources(
            """
            async def update(self, field_id: int, *, value: str) -> None:
                folder = (
                    f"/users/{path_segment(self._username)}"
                    f"/collection/folders/{path_segment(self._folder_id)}"
                )
                instance = f"/releases/{path_segment(self._release_id)}/instances/{path_segment(self._instance_id)}"
                await self._post(
                    f"{folder}{instance}/fields/{path_segment(field_id)}",
                    json={"value": value},
                )
            """
        )
    )
    assert endpoint_map.routes() == {
        "/users/{}/collection/folders/{}/releases/{}/instances/{}/fields/{}"
    }


def test_shared_submission_helper_keeps_its_own_verb_and_path() -> None:
    rows = _rows(
        """
        async def create(self, *, file: str) -> int:
            return await self._submit("/inventory/upload/add", file)

        async def delete(self, *, file: str) -> int:
            return await self._submit("/inventory/upload/delete", file)

        async def _submit(self, path: str, file: str) -> int:
            await self._post_file(path, file_path=file)
            return 1
        """
    )
    assert rows == [
        ("POST", "/inventory/upload/add", "client.things.create(file=...)"),
        ("POST", "/inventory/upload/delete", "client.things.delete(file=...)"),
    ]


def test_verbs_sharing_a_route_each_get_a_row() -> None:
    rows = _rows(
        """
        async def update(self, rating_id: int, rating: int) -> None:
            await self._put(self._path(rating_id), json={"rating": rating})

        async def delete(self, rating_id: int) -> None:
            await self._delete(self._path(rating_id))

        def _path(self, rating_id: int) -> str:
            return f"/ratings/{path_segment(rating_id)}"
        """
    )
    assert [(verb, route) for verb, route, _ in rows] == [
        ("PUT", "/ratings/{rating_id}"),
        ("DELETE", "/ratings/{rating_id}"),
    ]


def test_state_from_the_parent_is_not_an_argument_of_the_same_name() -> None:
    # ``folder_id`` in the route is the parent's; the optional ``folder_id``
    # argument is a different thing, so the call must not show it.
    rows = _rows(
        """
        async def update(
            self, instance_id: int, *, folder_id: int | None = None
        ) -> None:
            await self._post(
                f"/folders/{path_segment(self._folder_id)}"
                f"/instances/{path_segment(instance_id)}"
            )
        """
    )
    assert rows == [
        (
            "POST",
            "/folders/{folder_id}/instances/{instance_id}",
            "client.things.update(instance_id, ...)",
        )
    ]


def test_resource_no_chain_reaches_fails_loudly() -> None:
    sources = _sources(
        """
        async def get(self) -> None:
            await self._get_list("/things", Thing, "things")
        """,
        """
class Orphan(AsyncAPIResource):
    async def get(self) -> None:
        await self._get_list("/orphans", Thing, "things")
        """,
    )
    with pytest.raises(gen.ExtractionError, match="Orphan"):
        gen.build_map(sources)


def test_public_method_without_a_request_fails_loudly() -> None:
    with pytest.raises(gen.ExtractionError, match="Things.helper"):
        gen.build_map(
            _sources(
                """
                def helper(self) -> int:
                    return 1
                """
            )
        )


PROXY = """
class ThingProxy(AsyncLazyResource[Thing]):
    def __init__(self, client, thing_id: int) -> None:
        super().__init__(client, f"/things/{path_segment(thing_id)}", Thing)
        self._thing_id = thing_id
"""


@pytest.mark.parametrize(
    ("body", "extra", "client", "expected"),
    [
        pytest.param(
            """
            def list(self, *, page: int | None = None) -> AsyncPage[Thing]:
                return AsyncPage(client=self._client, path="/things", model_cls=Thing)
            """,
            "",
            "",
            ("GET", "/things", "client.things.list(...)", "SyncPage[Thing]", True),
            id="page-constructor",
        ),
        pytest.param(
            """
            def get(self, thing_id: int) -> ThingProxy:
                return ThingProxy(self._client, thing_id)
            """,
            PROXY,
            "",
            (
                "GET",
                "/things/{thing_id}",
                "client.things.get(thing_id)",
                "Thing (lazy)",
                False,
            ),
            id="lazy-proxy-forwarding-its-path-through-super-init",
        ),
        pytest.param(
            """
            async def download(self, thing_id: int) -> bytes:
                return await self._get_binary(f"/things/{path_segment(thing_id)}/file")
            """,
            "",
            "",
            (
                "GET",
                "/things/{thing_id}/file",
                "client.things.download(thing_id)",
                "bytes",
                False,
            ),
            id="binary-download",
        ),
        pytest.param(
            """
            async def identity(self) -> Identity:
                response = await self._client._send(
                    "GET", self._client._build_url("/oauth/identity")
                )
                return Identity.model_validate(response.json())
            """,
            "",
            "",
            (
                "GET",
                "/oauth/identity",
                "client.things.identity()",
                "Identity",
                False,
            ),
            id="direct-send",
        ),
        pytest.param(
            """
            async def list(self) -> builtins.list[Thing]:
                return await self._get_list("/things", Thing, "things")
            """,
            "",
            "",
            (
                "GET",
                "/things",
                "client.things.list()",
                "list[Thing]",
                False,
            ),
            id="builtins-list-return",
        ),
    ],
)
def test_request_patterns_and_return_column(
    body: str, extra: str, client: str, expected: tuple[str, str, str, str, bool]
) -> None:
    assert _full(body, extra, client) == [expected]


def test_callable_resource_is_documented_through_its_caller() -> None:
    rows = _full(
        """
        async def get(self) -> None:
            await self._get_list("/things", Thing, "things")
        """,
        """
class SearchThing(AsyncAPIResource):
    def __call__(self, **params) -> AsyncPage[Hit]:
        return AsyncPage(client=self._client, path="/search", model_cls=Hit)
        """,
        """
    def search(self, **params) -> AsyncPage[Hit]:
        return SearchThing(self)(**params)
        """,
    )
    assert ("GET", "/search", "client.search(...)", "SyncPage[Hit]", True) in rows
    assert all("SearchThing" not in call for _, _, call, _, _ in rows)


def test_unresolvable_path_fails_loudly() -> None:
    # ``+=`` leaves ``path`` unknown; a bogus ``{path}`` route would be worse
    # than stopping.
    with pytest.raises(gen.ExtractionError, match="cannot resolve the request path"):
        gen.build_map(
            _sources(
                """
                async def get(self) -> None:
                    path = "/a"
                    path += f"/{self._x}"
                    await self._get_list(path, Thing, "things")
                """
            )
        )


def test_async_return_type_without_a_sync_name_fails_loudly() -> None:
    with pytest.raises(gen.ExtractionError, match="AsyncOther"):
        gen.build_map(
            _sources(
                """
                def list(self) -> AsyncOther[Thing]:
                    return AsyncPage(client=self._client, path="/things", model_cls=Thing)
                """
            )
        )


OAUTH = """
_REQUEST_TOKEN_PATH = "/oauth/request_token"
_ACCESS_TOKEN_PATH = "/oauth/access_token"


async def _send(method: str, url: str, auth_header: str) -> None: ...


async def get_request_token(
    consumer_key: str, *, base_url: str = "https://api.discogs.com"
) -> RequestToken:
    response = await _send(
        "GET", f"{base_url.rstrip('/')}{_REQUEST_TOKEN_PATH}", "header"
    )


async def get_access_token(
    consumer_key: str, verifier: str, *, base_url: str = "https://api.discogs.com"
) -> AccessToken:
    response = await _send(
        "POST", f"{base_url.rstrip('/')}{_ACCESS_TOKEN_PATH}", "header"
    )
"""


def _oauth_sources() -> dict[str, str]:
    sources = _sources(
        """
        async def get(self) -> None:
            await self._get_list("/things", Thing, "things")
        """
    )
    sources["_oauth"] = textwrap.dedent(OAUTH)
    return sources


def test_oauth_helpers_are_listed_apart_from_client_operations() -> None:
    exported = {
        "get_request_token",
        "async_get_request_token",
        "get_access_token",
        "async_get_access_token",
    }
    endpoint_map = gen.build_map(_oauth_sources(), exported)
    assert [(r.verb, r.route, r.call, r.returns) for r in endpoint_map.oauth] == [
        (
            "POST",
            "/oauth/access_token",
            "discogs_sdk.oauth.get_access_token(consumer_key, verifier, ...)",
            "AccessToken",
        ),
        (
            "GET",
            "/oauth/request_token",
            "discogs_sdk.oauth.get_request_token(consumer_key, ...)",
            "RequestToken",
        ),
    ]
    assert all(r.route != "/oauth/request_token" for r in endpoint_map.operations)
    assert "/oauth/request_token" in endpoint_map.routes()


def test_oauth_helper_missing_from_the_public_module_fails_loudly() -> None:
    with pytest.raises(gen.ExtractionError, match="get_request_token"):
        gen.build_map(_oauth_sources(), {"get_access_token", "async_get_access_token"})
