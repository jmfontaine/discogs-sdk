"""Authentication — every way to authenticate with the Discogs API.

Covers:
  - Personal access token (simplest, read + limited write)
  - Consumer key/secret (app-level, no user context)
  - Full OAuth 1.0a flow (read + write on behalf of a user)
  - Environment variables
"""

from discogs_sdk import Discogs
from discogs_sdk.oauth import (
    AccessToken,
    RequestToken,
    get_access_token,
    get_request_token,
)


# ━━ 1. Personal access token ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Generate at https://www.discogs.com/settings/developers
# Simplest option.  Good for scripts and personal tools.
client = Discogs(token="YOUR_PERSONAL_TOKEN")


# ━━ 2. Consumer key / secret (no user context) ━━━━━━━━━━━━━━━━━━━━
# Register your app at https://www.discogs.com/settings/developers
# This identifies your app but does NOT act on behalf of any user.
# Read-only access to public data with higher rate limits than anonymous.
client = Discogs(
    consumer_key="YOUR_CONSUMER_KEY",
    consumer_secret="YOUR_CONSUMER_SECRET",
)


# ━━ 3. Full OAuth 1.0a flow ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Required for write operations (marketplace, collection, wantlist).
#
# Step 1: Get a request token.
request_token: RequestToken = get_request_token(
    consumer_key="YOUR_CONSUMER_KEY",
    consumer_secret="YOUR_CONSUMER_SECRET",
    callback_url="https://your-app.com/callback",  # or "oob" for CLI apps
)

# Step 2: Redirect the user to authorize your app.
print(f"Visit: {request_token.authorize_url}")

# Step 3: User authorizes and you receive a verifier code.
verifier = input("Enter the verifier code: ")

# Step 4: Exchange for an access token.
access: AccessToken = get_access_token(
    consumer_key="YOUR_CONSUMER_KEY",
    consumer_secret="YOUR_CONSUMER_SECRET",
    request_token=request_token.oauth_token,
    request_token_secret=request_token.oauth_token_secret,
    verifier=verifier,
)

# Step 5: Create a client with full OAuth credentials.
client = Discogs(
    consumer_key="YOUR_CONSUMER_KEY",
    consumer_secret="YOUR_CONSUMER_SECRET",
    access_token=access.oauth_token,
    access_token_secret=access.oauth_token_secret,
)

# Now you can access user-specific endpoints:
me = client.user.identity()
print(f"Authenticated as: {me.username}")


# ━━ 4. Environment variables ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# The SDK reads these automatically when no explicit args are passed:
#
#   DISCOGS_TOKEN              — personal access token
#   DISCOGS_CONSUMER_KEY       — OAuth consumer key
#   DISCOGS_CONSUMER_SECRET    — OAuth consumer secret
#   DISCOGS_ACCESS_TOKEN       — OAuth access token
#   DISCOGS_ACCESS_TOKEN_SECRET — OAuth access token secret
#
# Just set the env vars and create a bare client:
client = Discogs()  # picks up credentials from the environment

# Priority order: constructor args > environment variables.
