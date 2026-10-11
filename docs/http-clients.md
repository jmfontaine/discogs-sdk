# Custom HTTP clients

An injected `http_client` must be an `httpx2` client — the SDK is built on [httpx2](https://github.com/pydantic/httpx2),
Pydantic's maintained continuation of httpx. It owns its transport configuration and its lifecycle: `client.close()`
never closes it. SDK credentials, User-Agent and media type are still applied per request, so they describe the request
without mutating your client's defaults, and its own `httpx2.Auth` cannot replace credentials you gave the SDK.

An injected client's timeout is part of that transport configuration. The `timeout` argument only configures a client
the SDK creates, so `Discogs(http_client=httpx2.Client(timeout=99.0), timeout=1.0)` sends every request with the
injected client's 99-second timeout, even though `client.timeout` reports `1.0`. To control the timeout of an injected
client, set it on that client.

When the SDK has no credentials of its own, your client's authentication is preserved and its responses are never
cached, even with `cache=True`, because the SDK cannot tell whose account they belong to. Inside `cache_only()` every
request from such a client therefore raises `CacheMissError`.
