"""OAuth 1.0a helpers — re-exports for sync and async variants."""

from discogs_sdk._sync._oauth import (
    AccessToken,
    RequestToken,
    get_access_token,
    get_request_token,
)
from discogs_sdk._async._oauth import (
    get_access_token as async_get_access_token,
    get_request_token as async_get_request_token,
)

__all__ = [
    "AccessToken",
    "RequestToken",
    "async_get_access_token",
    "async_get_request_token",
    "get_access_token",
    "get_request_token",
]
