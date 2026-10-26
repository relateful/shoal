"""What the per-resource endpoint classes need from a client: a way to send one request.

`RestClient` is assembled from one class per Discord resource (`shoal.rest.resources`), so each
resource's methods live next to each other instead of in one very long file. Each of those classes
builds on `Requester`, which `RestClient` implements with rate limiting, retries and errors.

Discord: https://docs.discord.com/developers/reference#http-api
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from urllib.parse import urlencode

import msgspec

from shoal.payloads.message import AttachmentRequest
from shoal.rest.files import File
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
        files: Mapping[str, File] | None = None,
        form: Mapping[str, str] | None = None,
    ) -> T:
        """Send a request and decode the JSON response into `response_type`.

        With `files`, the body goes in the `payload_json` part of a `multipart/form-data` request,
        next to one part per file, named by the mapping's keys. `form` adds plain text fields, for
        endpoints that take their parameters as form fields rather than `payload_json`.
        """

    @abstractmethod
    async def request_empty(
        self,
        route: CompiledRoute,
        *,
        body: object = None,
        query: Mapping[str, QueryValue] | None = None,
        reason: str | None = None,
        files: Mapping[str, File] | None = None,
        form: Mapping[str, str] | None = None,
    ) -> None:
        """Send a request whose successful response has no body (204)."""

    @abstractmethod
    async def request_bytes(
        self, route: CompiledRoute, *, query: Mapping[str, QueryValue] | None = None
    ) -> bytes:
        """Send a request and return the body undecoded, for endpoints that do not answer JSON."""


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


def form_of(params: msgspec.Struct) -> dict[str, str]:
    """The set fields of a form payload, as text form fields."""
    return {
        field.encode_name: _query_scalar(value) if isinstance(value, bool) else str(value)
        for field in msgspec.structs.fields(params)
        if (value := getattr(params, field.name)) is not msgspec.UNSET
    }


def query_of(params: msgspec.Struct) -> dict[str, QueryValue]:
    """The set fields of a query payload, ready for `encode_query`."""
    query: dict[str, QueryValue] = {}
    for field in msgspec.structs.fields(params):
        value: object = getattr(params, field.name)
        if value is msgspec.UNSET:
            continue
        if isinstance(value, datetime):
            value = value.isoformat()
        query[field.encode_name] = msgspec.convert(value, QueryValue)
    return query


def with_attachments[P: msgspec.Struct](
    params: P, files: Sequence[File], *, describe: bool = True
) -> tuple[P, dict[str, File]]:
    """Name `files` `files[0]`, `files[1]`… and describe them in `params.attachments`.

    The descriptions are only filled in when `params.attachments` is unset and `describe` is true.
    Edits pass `describe=False`: there `attachments` lists every attachment to keep, so filling it
    with the new files alone would remove the existing ones, while leaving it out appends them.

    Discord: https://docs.discord.com/developers/reference#uploading-files
    """
    if not files:
        return params, {}
    named = {f"files[{index}]": file for index, file in enumerate(files)}
    if describe and getattr(params, "attachments", msgspec.UNSET) is msgspec.UNSET:
        described = [
            AttachmentRequest(
                id=index,
                filename=file.upload_name,
                description=msgspec.UNSET if file.description is None else file.description,
            )
            for index, file in enumerate(files)
        ]
        params = msgspec.structs.replace(params, attachments=described)
    return params, named
