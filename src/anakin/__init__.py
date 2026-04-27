"""
Anakin Python SDK.

Quickstart:
    from anakin import Anakin

    client = Anakin(api_key="ak-...")
    doc = client.scrape("https://example.com", formats=["markdown"])
    print(doc.markdown)

API key resolution: explicit `api_key=` argument > `ANAKIN_API_KEY` env var.
"""

from anakin._version import __version__
from anakin.client import Anakin
from anakin.errors import (
    AnakinError,
    AuthenticationError,
    ConfigurationError,
    InsufficientCreditsError,
    InvalidRequestError,
    JobFailedError,
    JobTimeoutError,
    NetworkError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    WireAuthRequiredError,
)
from anakin.models import (
    CrawlPage,
    CrawlResult,
    Document,
    MapResult,
    WireError,
    WireResult,
)

__all__ = [
    "Anakin",
    # Errors
    "AnakinError",
    "AuthenticationError",
    "ConfigurationError",
    # Models
    "CrawlPage",
    "CrawlResult",
    "Document",
    "InsufficientCreditsError",
    "InvalidRequestError",
    "JobFailedError",
    "JobTimeoutError",
    "MapResult",
    "NetworkError",
    "NotFoundError",
    "PermissionError",
    "RateLimitError",
    "ServerError",
    "WireAuthRequiredError",
    "WireError",
    "WireResult",
    "__version__",
]
