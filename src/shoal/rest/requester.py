"""What the per-resource endpoint classes need from a client: a way to send one request.

`RestClient` is assembled from one class per Discord resource (`shoal.rest.resources`), so each
resource's methods live next to each other instead of in one very long file. Each of those classes
builds on `Requester`, which `RestClient` implements with rate limiting, retries and errors.

Discord: https://docs.discord.com/developers/reference#http-api
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
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
    async def request_optional[T](
        self,
        route: CompiledRoute,
        response_type: type[T],
        *,
        body: object = None,
        reason: str | None = None,
    ) -> T | None:
        """Send a request that answers with `response_type`, or with no body (204) for `None`."""

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
    """The set fields of a form payload, as text form fields.

    Raises:
        TypeError: A field holds something a form field cannot carry, such as a list or `None`.
    """
    form: dict[str, str] = {}
    for name, value in _set_fields(params):
        form[name] = _query_scalar(_scalar(name, value))
    return form


def query_of(params: msgspec.Struct) -> dict[str, QueryValue]:
    """The set fields of a query payload, ready for `encode_query`.

    A datetime is sent in ISO 8601; give it a time zone, as Discord reads one without as UTC.

    Raises:
        TypeError: A field holds something a query cannot carry, such as `None` or a nested list.
    """
    return {name: _query_value(name, value) for name, value in _set_fields(params)}


def comma_joined(query: dict[str, QueryValue], name: str) -> dict[str, QueryValue]:
    """Send the list under `name` as one comma-separated value, as a few endpoints require.

    An empty list is left out, like every other empty list in a query.
    """
    value = query.pop(name, None)
    if isinstance(value, Sequence) and not isinstance(value, str) and value:
        query[name] = ",".join(str(item) for item in value)
    return query


def _set_fields(params: msgspec.Struct) -> list[tuple[str, object]]:
    """Each set field's wire name and value, with datetimes as ISO 8601 text."""
    fields: list[tuple[str, object]] = []
    for field in msgspec.structs.fields(params):
        value: object = getattr(params, field.name)
        if value is msgspec.UNSET:
            continue
        fields.append((field.encode_name, value.isoformat() if isinstance(value, datetime) else value))
    return fields


def _scalar(name: str, value: object) -> QueryScalar:
    try:
        converted: QueryScalar = msgspec.convert(value, QueryScalar)
    except msgspec.ValidationError as error:
        msg = f"{name} cannot be sent as text: {error}"
        raise TypeError(msg) from error
    return converted


def _query_value(name: str, value: object) -> QueryValue:
    try:
        converted: QueryValue = msgspec.convert(value, QueryValue)
    except msgspec.ValidationError as error:
        msg = f"{name} cannot be sent in a query: {error}"
        raise TypeError(msg) from error
    return converted


def with_attachments[P: msgspec.Struct](
    params: P, files: Sequence[File], *, edit: bool = False
) -> tuple[P, dict[str, File]]:
    """Name `files` `files[0]`, `files[1]`… and describe them in `params.attachments`.

    When creating, an unset `attachments` is filled in with one entry per file, carrying its name
    and alt text. When editing (`edit=True`), `attachments` lists every attachment the message keeps:
    left unset, Discord keeps the existing ones and adds the files, but alt text cannot be sent; when
    the caller sets it, the new files are added to the caller's list so they are not dropped. An
    entry the caller already wrote for a file's index is left as it is, in both cases.

    Discord: https://docs.discord.com/developers/reference#editing-message-attachments
    """
    if not files:
        return params, {}
    named = {f"files[{index}]": file for index, file in enumerate(files)}
    current: object = getattr(params, "attachments", msgspec.UNSET)
    if isinstance(current, list):
        items = cast(
            "list[object]", current
        )  # isinstance narrows to list[Unknown]; the items are checked below
        given: list[AttachmentRequest] = [item for item in items if isinstance(item, AttachmentRequest)]
        if not edit:
            return params, named
    elif edit:
        return params, named
    else:
        given = []
    listed = {item.id for item in given}
    added = [_describe(index, file) for index, file in enumerate(files) if index not in listed]
    return msgspec.structs.replace(params, attachments=[*given, *added]), named


def _describe(index: int, file: File) -> AttachmentRequest:
    return AttachmentRequest(
        id=index,
        filename=file.upload_name,
        description=msgspec.UNSET if file.description is None else file.description,
    )
