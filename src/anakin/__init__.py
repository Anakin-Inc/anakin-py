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
from anakin.countries import SUPPORTED_COUNTRIES, SUPPORTED_COUNTRY_CODES
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
    AgenticSearchData,
    AgenticSearchResult,
    BrowserSession,
    BrowserSessionHandle,
    Country,
    CrawlPage,
    CrawlResult,
    Document,
    MapResult,
    SearchResult,
    SearchResultItem,
    WireError,
    WireResult,
)

__all__ = [
    "SUPPORTED_COUNTRIES",
    "SUPPORTED_COUNTRY_CODES",
    "AgenticSearchData",
    "AgenticSearchResult",
    "Anakin",
    "AnakinError",
    "AuthenticationError",
    "BrowserSession",
    "BrowserSessionHandle",
    "ConfigurationError",
    "Country",
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
    "SearchResult",
    "SearchResultItem",
    "ServerError",
    "WireAuthRequiredError",
    "WireError",
    "WireResult",
    "__version__",
]
