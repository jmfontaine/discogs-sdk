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
different account or mode. See [`examples/authentication.py`](../examples/authentication.py) for the full OAuth flow.

> [!TIP]
> Use a `.env` file with [python-dotenv](https://pypi.org/project/python-dotenv/) or
> [direnv](https://direnv.net/) to avoid exporting tokens manually in every shell.

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
            print(want.basic_information.title)


asyncio.run(main())
```
