# discogs-sdk documentation

1. [Getting started](getting-started.md): behaviors to know, installation, fetching resources, search, sub-resources, async usage
2. [Pagination](pagination.md): what a page costs, stopping early, page attributes
3. [Authentication](authentication.md): personal token, consumer key/secret, OAuth 1.0a, credential precedence
4. [Collection and marketplace](collection-and-marketplace.md): folders, instances, wantlist, listings, orders
5. [Errors and retries](errors-and-retries.md): rate limits, retries, settling an ambiguous write, the exception hierarchy
6. [Configuration](configuration.md): every client parameter
7. [Caching](caching.md): the response cache, `no_cache()`, `cache_only()`, custom backends
8. [Observability](observability.md): `client.ratelimit` and `on_request` events
9. [Concurrency](concurrency.md): sharing a client across threads and tasks
10. [Custom HTTP clients](http-clients.md): injecting an `httpx2` client
11. [Models](models.md): field naming, timestamps, original API values
12. [Migrating from python3-discogs-client](migrating-from-python3-discogs-client.md): idiom-by-idiom translation and behaviour differences
13. [Endpoint map](endpoints.md): which SDK call reaches which Discogs endpoint, with verbs, access chains and return types
