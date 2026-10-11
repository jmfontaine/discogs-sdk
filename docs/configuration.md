# Configuration

Every parameter of `Discogs` and `AsyncDiscogs`, all keyword-only:

| Parameter | Default | Description |
|---|---|---|
| `access_token_secret` | `None` | OAuth access token secret |
| `access_token` | `None` | OAuth access token |
| `base_url` | `https://api.discogs.com` | API base URL; pagination `next` links are rebased onto it, and a link to any origin other than it or `https://api.discogs.com` raises `DiscogsError` |
| `cache_dir` | `None` | Directory for SQLite cache; in-memory when omitted. Used only with `cache=True` |
| `cache_ttl` | `3600.0` | Cache time-to-live in seconds. Used only with `cache=True` |
| `cache` | `False` | `True` builds the built-in backend from `cache_dir` and `cache_ttl`; or pass a `ResponseCache` instance (see [Custom backends](caching.md#custom-backends)), which carries its own TTL and storage and is never closed by the client |
| `consumer_key` | `None` | OAuth consumer key |
| `consumer_secret` | `None` | OAuth consumer secret |
| `http_client` | `None` | Custom `httpx2.Client` or `httpx2.AsyncClient` |
| `max_retries` | `3` | Retries after the first attempt, `>= 0` (`0` disables retries, a negative value raises `ValueError`), so `max_retries=N` allows up to N + 1 attempts: up to 4 by default. Reads retry on 429, 500, 502, 503 and 504, network errors, timeouts and dropped connections, mutations only on pre-send failures; any other failure stops at once, and so does a `Retry-After` above 60s. See [Errors and retries](errors-and-retries.md#rate-limits-and-retries) |
| `media_type` | `"discogs"` | Format of text fields: `"discogs"` (Discogs markup), `"html"` or `"plaintext"`; sent in the `Accept` header, and cached responses are kept apart per value |
| `on_request` | `None` | Callback receiving a `RequestEvent` per request |
| `timeout` | `30.0` | Request timeout in seconds for the HTTP client the SDK creates; an injected `http_client` keeps its own (see [Custom HTTP clients](http-clients.md)) |
| `token` | `None` | Personal access token |
| `user_agent` | `discogs-sdk/<version> +https://github.com/jmfontaine/discogs-sdk` | `User-Agent` header; a non-empty value replaces the default entirely |

With `cache=False`, the default, `cache_dir` and `cache_ttl` are ignored and no cache or directory is created; a
`ResponseCache` instance ignores them too. `cache_ttl=0` is accepted and expires every entry at once, so each read
refetches: it is not a way to say "no limit".

See [Authentication](authentication.md) for how a credential mode is selected.
