"""Advanced — error handling, caching, custom clients, exports, and lists.

Covers:
  - Exception hierarchy and catching patterns
  - Rate limit handling
  - Custom User-Agent
  - HTTP caching with hishel
  - Custom httpx client
  - Exports (inventory CSV download)
  - Uploads (inventory CSV import)
  - Lists
  - User profile and contributions
  - Submissions by type (artists, labels)
"""

import httpx

from discogs_sdk import (
    AuthenticationError,
    Discogs,
    DiscogsAPIError,
    DiscogsConnectionError,
    DiscogsError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

# Reads DISCOGS_TOKEN from the environment, or pass token="..." explicitly.
client = Discogs()

# ━━ Exception hierarchy ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
#   DiscogsError (base)
#   +-- DiscogsConnectionError (network-level: timeout, DNS, etc.)
#   +-- DiscogsAPIError (HTTP error with status code + body)
#       +-- AuthenticationError (401)
#       +-- NotFoundError (404)
#       +-- ValidationError (422)
#       +-- RateLimitError (429)

# Catch specific errors first, broader ones last.
try:
    release = client.releases.get(999999999)
    _ = release.title  # triggers the GET
except NotFoundError:
    print("Release not found")
except AuthenticationError:
    print("Invalid or missing credentials")
except RateLimitError as exc:
    # The SDK retries 429s automatically (up to max_retries), but if
    # retries are exhausted this exception is raised.
    print(f"Rate limited.  Retry after: {exc.retry_after}")
except ValidationError as exc:
    print(f"Invalid request: {exc.status_code}: {exc.response_body}")
except DiscogsAPIError as exc:
    # Any other HTTP error (500, 502, 503, etc.)
    print(f"API error {exc.status_code}: {exc.response_body}")
except DiscogsConnectionError:
    print("Network error — check your connection")
except DiscogsError:
    print("Unexpected SDK error")


# ━━ Retry behavior ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# The SDK automatically retries on: 429, 500, 502, 503, 504.
# It also retries on connection errors and timeouts.
# Default: 3 retries with exponential backoff (2^attempt + jitter).
# The Retry-After header is respected when present.
client = Discogs(
    token="YOUR_TOKEN_HERE",
    max_retries=5,  # increase retries for flaky connections
    timeout=60.0,  # seconds per request
)


# ━━ HTTP caching with hishel ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Install: pip install discogs-sdk[cache]  (or: uv add discogs-sdk[cache])
# Caches responses locally, respecting HTTP cache headers.
cached_client = Discogs(token="YOUR_TOKEN_HERE", cache=True)

# Repeated calls for the same resource hit the cache:
r1 = cached_client.releases.get(352665)
_ = r1.title  # HTTP GET — cached
r2 = cached_client.releases.get(352665)
_ = r2.title  # served from cache


# ━━ Custom User-Agent ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Discogs requires a descriptive User-Agent.  The SDK sends a sensible
# default, but you can override it to identify your application.
client = Discogs(token="YOUR_TOKEN_HERE", user_agent="MyApp/1.0 +https://myapp.example.com")


# ━━ Custom httpx client ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pass your own httpx.Client for full control over transport, proxies,
# certificates, etc.  The SDK will NOT close a client you provide.
custom_http = httpx.Client(
    timeout=10.0,
    limits=httpx.Limits(max_connections=20),
)
client = Discogs(token="YOUR_TOKEN_HERE", http_client=custom_http)
# Remember to close it yourself when done:
custom_http.close()


# ━━ Exports (inventory CSV) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request a new inventory export.
client.exports.request()

# List available exports.
for export in client.exports.list():
    print(f"  Export #{export.id}: {export.status} ({export.created_at})")

# Get a specific export.
export = client.exports.get(12345)
print(f"Status: {export.status}")

# Download the CSV.
csv_bytes = client.exports.download(12345)
with open("inventory.csv", "wb") as f:
    f.write(csv_bytes)


# ━━ Uploads (inventory CSV import) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Upload a CSV to add items to your inventory.
client.uploads.create(file="add_items.csv")

# Upload a CSV to modify existing items.
client.uploads.change(file="update_items.csv")

# Upload a CSV to delete items.
client.uploads.delete(file="delete_items.csv")

# List recent uploads.
for upload in client.uploads.list():
    print(f"  Upload #{upload.id}: {upload.status} ({upload.filename})")

# Get details of a specific upload.
upload = client.uploads.get(67890)
print(f"Status: {upload.status}")


# ━━ Lists ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Get a public list by ID.
disc_list = client.lists.get(12345)
print(f"List: {disc_list.name}")
for item in disc_list.items:
    print(f"  {item.display_title} ({item.type})")

# List a user's lists (paginated).
user = client.users.get("susan.salkeld")
for summary in user.lists.list():
    print(f"  [{summary.id}] {summary.name}")


# ━━ User profile ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Get any user's public profile.
user = client.users.get("susan.salkeld")
print(f"{user.username}: {user.name}")
print(f"Location: {user.location}")

# Update your own profile (requires OAuth).
client.users.get("your_username").update(
    name="New Display Name",
    location="Brooklyn, NY",
    curr_abbr="USD",
)

# ━━ User contributions and submissions ━━━━━━━━━━━━━━━━━━━━━━━━━━━
user = client.users.get("susan.salkeld")

for contrib in user.contributions.list(sort="added", sort_order="desc"):
    print(f"  {contrib.title}")

for sub in user.submissions.list():
    print(f"  {sub.title}")

# Submissions broken down by type.
for artist in user.submissions.artists.list():
    print(f"  {artist.name}")

for label in user.submissions.labels.list():
    print(f"  {label.name}")
