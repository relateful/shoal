"""The pluggable HTTP transport underneath `RestClient`.

The client never touches aiohttp directly: it calls an `HTTPTransport`. Tests use an in-memory
transport, and deployments can swap in one that routes through a proxy or a service mesh.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, final, override

import aiohttp

from shoal.rest.defaults import REQUEST_TIMEOUT


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    """A raw HTTP response. Header names are lower-cased."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class HTTPTransport(Protocol):
    """Sends one HTTP request and returns the raw response.

    Implementations raise `OSError` (or a subclass) for connection failures so the client can retry
    them; they never raise for HTTP error statuses.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HTTPResponse:
        """Send the request and read the full response body."""
        ...

    async def close(self) -> None:
        """Release connections. Further requests are not allowed."""
        ...


class TransportError(OSError):
    """The request could not be completed at the network level."""


@final
class AiohttpTransport(HTTPTransport):
    """The default transport, backed by one shared `aiohttp.ClientSession`.

    Args:
        timeout: Total seconds allowed per request, including reading the body.
        proxy: Optional HTTP proxy URL.
    """

    __slots__ = ("_proxy", "_session", "_timeout")

    def __init__(self, *, timeout: float = REQUEST_TIMEOUT, proxy: str | None = None) -> None:
        """Create the transport; the session opens lazily on first use."""
        self._timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=timeout)
        self._proxy: str | None = proxy
        self._session: aiohttp.ClientSession | None = None

    @override
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HTTPResponse:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        try:
            async with self._session.request(
                method, url, headers=dict(headers), data=body, proxy=self._proxy
            ) as response:
                payload = await response.read()
                lowered = {key.lower(): value for key, value in response.headers.items()}
                return HTTPResponse(status=response.status, headers=lowered, body=payload)
        except (aiohttp.ClientError, TimeoutError) as error:
            # The URL can hold credentials (an interaction token in the path) and private search
            # terms (the query), and a response error's repr carries the request headers: none of it
            # belongs in a message that gets logged. The client adds the redacted route.
            if isinstance(error, aiohttp.ClientResponseError):
                detail = f"{type(error).__name__} (HTTP {error.status})"
            elif isinstance(error, aiohttp.InvalidURL):
                detail = type(error).__name__  # its text is the whole URL
            else:
                detail = str(error) or type(error).__name__
            msg = f"{method} request failed: {detail}"
            raise TransportError(msg) from error

    @override
    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
