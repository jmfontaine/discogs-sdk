# Concurrency

### Concurrency

One client may be shared by several threads (`Discogs`) or tasks (`AsyncDiscogs`). A few things are tied to a
context or an object rather than to the client.

`no_cache()` and `cache_only()` apply to the current execution context only. A task copies its context when it is
created, so a task created before the block does not see the scope. A pool worker runs in its own context, so
`with client.no_cache(): pool.map(...)` still serves the workers from the cache; on a free-threaded 3.14+ build, where
a new thread starts with a copy of its creator's context, a worker spawned inside the block keeps the scope for its
lifetime instead. Either way, enter the scope inside the worker, or run the work in a copy of the context taken inside
the scope. Take a new copy for each call: one `Context` cannot run in two threads at once, and sharing it raises
`RuntimeError`.

```python
import contextvars
from concurrent.futures import ThreadPoolExecutor


def title(release_id):
    return client.releases.get(release_id).title


with ThreadPoolExecutor() as pool:
    with client.no_cache():
        # copy_context() runs here, inside the scope
        future = pool.submit(contextvars.copy_context().run, title, 352665)
    print(future.result())  # The Downward Spiral, fetched from the API
```

An unresolved `AsyncDiscogs` proxy awaited from several tasks at once sends one request and hands every task the same
model (or the same exception; a failure is not kept, so the next await tries again). That request runs in the context
of the task that awaited first, so its `no_cache()` or `cache_only()` scope, or the lack of one, applies to all of them.
Enter the scope before the first await, or call `get()` again inside it for a proxy of your own. Cancelling one waiting
task leaves the request and the other tasks alone.

A page returned by `.list()` or `search()` is a single-pass iterator for one consumer. Several threads or tasks
iterating the same page race on its position and can fetch a page twice and yield its items twice, and a page that
is exhausted yields nothing on a second pass. Call `.list()` or `search()` again for each consumer and each pass.

`on_request` runs on the thread or task that made the request, once that request completes, so events arrive in
completion order rather than start order, and with several threads the callback can run in several of them at once.
`client.ratelimit` is the value from whichever live response completed last, not necessarily the one with the lowest
`remaining`: under concurrency it is a hint for pacing, not a global count.

The cache that `cache=True` builds locks internally. A custom `ResponseCache` needs its own locking whenever several
threads share it, and with `AsyncDiscogs` that is always the case: the async client may call the cache from worker
threads so that disk I/O never blocks the event loop, and it calls its methods without synchronisation.
