# discogs-sdk documentation

1. [Getting started](getting-started.md): installation, fetching resources, search, sub-resources, async usage
2. [Authentication](authentication.md): personal token, consumer key/secret, OAuth 1.0a, credential precedence
3. [Collection and marketplace](collection-and-marketplace.md): folders, instances, wantlist, listings, orders
4. [Errors and retries](errors-and-retries.md): rate limits, retries, the exception hierarchy
5. [Configuration](configuration.md): every client parameter
6. [Caching](caching.md): the response cache, `no_cache()`, `cache_only()`, custom backends
7. [Observability](observability.md): `client.ratelimit` and `on_request` events
8. [Concurrency](concurrency.md): sharing a client across threads and tasks
9. [Custom HTTP clients](http-clients.md): injecting an `httpx2` client
10. [Models](models.md): field naming, timestamps, original API values
