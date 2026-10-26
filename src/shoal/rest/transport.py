"""The pluggable HTTP transport underneath `RestClient`.

The client never touches aiohttp directly: it calls an `HTTPTransport`. Tests use an in-memory
transport, and deployments can swap in one that routes through a proxy or a service mesh.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, final, override

import aiohttp

from shoal.core.errors import ShoalError
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
    them; they never raise for HTTP error statuses. Raise `TransportError(request_sent=False)` when
    the connection failed before anything was sent, so requests that are not idempotent are retried
    too.
    """

    __slots__ = ()

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


class TransportError(ShoalError, OSError):
    """The request could not be completed at the network level.

    Args:
        message: What went wrong, without the URL.
        request_sent: `False` only when the connection failed before any of the request was sent,
            so Discord cannot have acted on it. The client retries requests that are not
            idempotent (a message, an interaction response) only then, so a retry never posts twice.
    """

    def __init__(self, message: str, *, request_sent: bool = True) -> None:
        """Create the error; see the class docstring for the arguments."""
        super().__init__(message)
        self.request_sent: bool = request_sent


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
            # terms (the query). aiohttp puts the full URL in the text of many of its errors (a
            # connection timeout, a response error, an invalid URL), so none of that text is kept,
            # and the original error is not chained, so a logged traceback cannot show it either.
            # The client adds the redacted route.
            msg = f"{method} request failed: {_describe(error)}"
            # A connector error means no connection was made, so nothing reached Discord.
            raise TransportError(
                msg, request_sent=not isinstance(error, aiohttp.ClientConnectorError)
            ) from None

    @override
    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None


def _describe(error: aiohttp.ClientError | TimeoutError) -> str:
    """What went wrong, without any part of the URL beyond the host and port."""
    name = type(error).__name__
    if isinstance(error, aiohttp.ClientResponseError):
        return f"{name} (HTTP {error.status})"
    if isinstance(error, aiohttp.ClientConnectorError):
        cause = type(error.os_error).__name__
        return f"{name} to {error.host}:{error.port} ({cause})"
    return name
