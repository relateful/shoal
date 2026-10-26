"""What the per-resource endpoint classes need from a client: a way to send one request.

`RestClient` is assembled from one class per Discord resource (`shoal.rest.resources`), so each
resource's methods live next to each other instead of in one very long file. Each of those classes
builds on `Requester`, which `RestClient` implements with rate limiting, retries and errors.

Discord: https://docs.discord.com/developers/reference#http-api
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from urllib.parse import urlencode

import msgspec

from shoal.rest.route import CompiledRoute

type QueryScalar = str | int | bool
"""One query string value. Booleans are sent as `true`/`false` and snowflakes as their digits.

Discord: https://docs.discord.com/developers/reference#boolean-query-strings
"""

type QueryValue = QueryScalar | Sequence[QueryScalar]
"""A query string value; a sequence is sent as the same parameter repeated (`?id=1&id=2`).

Discord: https://docs.discord.com/developers/reference#array-query-strings
"""


class Requester(ABC):
    """Sends requests for the endpoint classes. `RestClient` is the implementation."""

    __slots__ = ()

    @abstractmethod
    async def request[T](
        self,
        route: CompiledRoute,
        response_type: type[T],
        *,
        body: object = None,
        query: Mapping[str, QueryValue] | None = None,
        reason: str | None = None,
    ) -> T:
        """Send a request and decode the JSON response into `response_type`."""

    @abstractmethod
    async def request_empty(
        self,
        route: CompiledRoute,
        *,
        body: object = None,
        query: Mapping[str, QueryValue] | None = None,
        reason: str | None = None,
    ) -> None:
        """Send a request whose successful response has no body (204)."""


def _query_scalar(value: QueryScalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def encode_query(query: Mapping[str, QueryValue]) -> str:
    """Encode `query` as Discord expects it: booleans as `true`/`false`, sequences repeated."""
    pairs: list[tuple[str, str]] = []
    for key, value in query.items():
        if isinstance(value, str | int):
            pairs.append((key, _query_scalar(value)))
        else:
            pairs.extend((key, _query_scalar(item)) for item in value)
    return urlencode(pairs)


def query_of(params: msgspec.Struct) -> dict[str, QueryValue]:
    """The set fields of a query payload, ready for `encode_query`."""
    query: dict[str, QueryValue] = {}
    for field in msgspec.structs.fields(params):
        value: object = getattr(params, field.name)
        if value is msgspec.UNSET:
            continue
        query[field.encode_name] = msgspec.convert(value, QueryValue)
    return query
