# Authentication

### Authentication

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
different account or mode. See [`examples/authentication.py`](https://github.com/jmfontaine/discogs-sdk/blob/main/examples/authentication.py) for the full OAuth flow.

> [!TIP]
> Use a `.env` file with [python-dotenv](https://pypi.org/project/python-dotenv/) or
> [direnv](https://direnv.net/) to avoid exporting tokens manually in every shell.
