# Authentication

Set your personal access token from [your Discogs developer settings](https://www.discogs.com/settings/developers) as an environment variable:

```bash
export DISCOGS_TOKEN="your-token-here"
```

```python
from discogs_sdk import Discogs

client = Discogs()  # reads DISCOGS_TOKEN from environment
```

You can also pass credentials explicitly:

```python
client = Discogs(token="your-token-here")
```

The SDK supports three auth modes: personal token, consumer key/secret, and OAuth 1.0a. Exactly one mode is selected
when the client is constructed, and only that mode's credentials are used. The precedence is:

1. An explicit `token` selects personal-token auth and overrides every environment credential.
2. Explicit OAuth access-token credentials select OAuth; any missing half may come from the matching `DISCOGS_*`
   variable, but an unrelated environment token never takes over.
3. Explicit `consumer_key`/`consumer_secret` select consumer auth, without borrowing environment access tokens.
4. With no auth arguments, the environment resolves the mode: `DISCOGS_TOKEN`, then a complete OAuth set, then
   `DISCOGS_CONSUMER_KEY`/`DISCOGS_CONSUMER_SECRET`, then unauthenticated.

An explicitly selected but incomplete credential set raises `ValueError` rather than quietly falling back to a
different account or mode. [OAuth 1.0a](#oauth-10a) below walks through obtaining OAuth access-token credentials.

> [!TIP]
> Use a `.env` file with [python-dotenv](https://pypi.org/project/python-dotenv/) or
> [direnv](https://direnv.net/) to avoid exporting tokens manually in every shell.

## What each mode can reach

| Credentials | Rate limit | Image URLs | User-scoped access |
|---|---|---|---|
| None | 25/min | Resource reads only | No |
| Consumer key/secret only | 60/min | Yes | No |
| Personal token | 60/min | Yes | Yes (token holder only) |
| Full OAuth | 60/min | Yes | Yes (any authorized user) |

User-scoped access means acting as an account: reading its private collection or wantlist, every collection folder
beyond 0 ("All") and its private notes, writing to its collection or wantlist, its marketplace orders and listing
writes, and `client.user.identity()`. A public collection's folder 0 and a public wantlist stay readable without it.
Consumer credentials identify your application, not a user, so they raise the rate limit and unlock image URLs but
reach none of those. A personal token acts as the one account that generated it, with everything that account can do.
OAuth acts as whichever user authorized your application.

Without credentials, image URLs come back on resource reads such as `client.releases.get(352665)`, but search results
carry empty `cover_image` and `thumb` strings. The rate limits are moving averages over 60 seconds; see
[Errors and retries](errors-and-retries.md#rate-limits-and-retries) for how the SDK handles a 429.

## The selected mode

`client.auth_mode` reports the mode the client selected, as the exported `AuthMode` literal: `"token"`, `"consumer"`,
`"oauth"` or `"none"`. It is a plain attribute read on both `Discogs` and `AsyncDiscogs`, with no `await`: it sends no
request and exposes no credential. Ask the client rather than checking `DISCOGS_TOKEN` yourself: with only
`DISCOGS_CONSUMER_KEY`/`DISCOGS_CONSUMER_SECRET` set, the client still authenticates, and `auth_mode` is `"consumer"`.

```python
from discogs_sdk import AuthMode, Discogs

client = Discogs(
    consumer_key="your-consumer-key", consumer_secret="your-consumer-secret"
)
mode: AuthMode = client.auth_mode
print(mode)  # "consumer"
```

It reflects only the credentials the SDK attaches. Authentication configured on an injected `http_client` is not
counted: a client given no credentials of its own reports `"none"` even when the injected client authenticates.

## The authenticated user

`client.user.identity()` asks Discogs who the credentials belong to (`GET /oauth/identity`) and returns an `Identity`
with `id`, `username`, `consumer_name` and `resource_url`. It needs a personal token or OAuth, and unlike `.get()` it
sends its request at once. `Identity` holds no collection or wantlist; build a user from its `username` for those:

```python
from discogs_sdk import Discogs

client = Discogs()  # reads DISCOGS_TOKEN from the environment
identity = client.user.identity()  # the request is sent here
print(identity.username)  # "trent_reznor"

user = client.users.get(identity.username)
for want in user.wantlist.list():
    if want.basic_information:  # None when Discogs omits it
        print(want.basic_information.title)
```

With `AsyncDiscogs`, `identity()` is a coroutine: await it before reading `username`.
`client.user.identity().username` without the `await` raises `AttributeError`, since a coroutine has no `username`.

```python
import asyncio

from discogs_sdk import AsyncDiscogs


async def main():
    async with AsyncDiscogs() as client:
        identity = await client.user.identity()
        user = client.users.get(identity.username)
        async for want in user.wantlist.list():
            if want.basic_information:
                print(want.basic_information.title)


asyncio.run(main())
```

## OAuth 1.0a

OAuth lets your application act for any Discogs user who authorizes it, without seeing their password. Register the
application in [your Discogs developer settings](https://www.discogs.com/settings/developers) to get a consumer key
and secret, then run the flow once per user with the helpers in `discogs_sdk.oauth`:

1. `get_request_token(consumer_key, consumer_secret, callback_url="oob")` returns a `RequestToken` with
   `oauth_token`, `oauth_token_secret` and `authorize_url`.
2. Send the user to `authorize_url`. After they approve, Discogs gives them a verifier to paste back into your
   application, or, when your application has a callback URL, redirects them to it, where you read the verifier from
   the request. Pass that URL as `callback_url`; the default `"oob"` (out of band) asks for no redirect.
3. `get_access_token(consumer_key, consumer_secret, request_token, request_token_secret, verifier)` exchanges the
   request token for an `AccessToken` with `oauth_token` and `oauth_token_secret`. Do it within 15 minutes of step 1:
   Discogs expires the request token and verifier after that.
4. Pass that pair to the client as `access_token` and `access_token_secret`, alongside the consumer key and secret.

```python
from discogs_sdk import Discogs
from discogs_sdk.oauth import get_access_token, get_request_token

CONSUMER_KEY = "your-consumer-key"
CONSUMER_SECRET = "your-consumer-secret"

request_token = get_request_token(CONSUMER_KEY, CONSUMER_SECRET)
print(f"Authorize this app at {request_token.authorize_url}")

verifier = "verifier-from-discogs"  # in a terminal: input("Verifier: ")
access = get_access_token(
    CONSUMER_KEY,
    CONSUMER_SECRET,
    request_token=request_token.oauth_token,
    request_token_secret=request_token.oauth_token_secret,
    verifier=verifier,
)

client = Discogs(
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=access.oauth_token,
    access_token_secret=access.oauth_token_secret,
)
print(client.auth_mode)  # "oauth"
```

A web application handles steps 1 and 3 in separate requests, so it keeps the request token's `oauth_token_secret`
(in the user's session, say) until the callback arrives. The access token pair does not expire unless the user
revokes your application's access, so store it: later clients take it as arguments or from `DISCOGS_ACCESS_TOKEN` and
`DISCOGS_ACCESS_TOKEN_SECRET`, with the consumer pair from `DISCOGS_CONSUMER_KEY` and `DISCOGS_CONSUMER_SECRET`, and
need no new authorization.

`async_get_request_token` and `async_get_access_token` take the same arguments and return the same `RequestToken` and
`AccessToken`, as coroutines for `AsyncDiscogs`:

```python
import asyncio

from discogs_sdk import AsyncDiscogs
from discogs_sdk.oauth import async_get_access_token, async_get_request_token

CONSUMER_KEY = "your-consumer-key"
CONSUMER_SECRET = "your-consumer-secret"


async def main():
    request_token = await async_get_request_token(CONSUMER_KEY, CONSUMER_SECRET)
    print(f"Authorize this app at {request_token.authorize_url}")

    verifier = "verifier-from-discogs"
    access = await async_get_access_token(
        CONSUMER_KEY,
        CONSUMER_SECRET,
        request_token=request_token.oauth_token,
        request_token_secret=request_token.oauth_token_secret,
        verifier=verifier,
    )

    async with AsyncDiscogs(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=access.oauth_token,
        access_token_secret=access.oauth_token_secret,
    ) as client:
        print(client.auth_mode)  # "oauth"


asyncio.run(main())
```

Each helper sends one request and never retries it. An error status raises from the SDK's usual hierarchy (401 →
`AuthenticationError`; an expired or malformed verifier gets a 400, which raises `DiscogsAPIError`) and a transport
failure raises `DiscogsConnectionError`; see [Error handling](errors-and-retries.md#error-handling).
[`examples/authentication.py`](../examples/authentication.py) runs the sync flow interactively, with that error
handling.
