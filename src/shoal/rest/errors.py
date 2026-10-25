"""Exceptions raised by the HTTP client.

Discord: https://docs.discord.com/developers/topics/opcodes-and-status-codes#http
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import TypeGuard

import msgspec

from shoal.core.errors import ShoalError
from shoal.payloads.errors import ErrorResponse, JSONErrorCode
from shoal.rest.route import CompiledRoute


@dataclass(frozen=True, slots=True)
class FieldError:
    """One validation error from Discord's nested `errors` object.

    Discord: https://docs.discord.com/developers/reference#error-messages
    """

    path: str
    """Dotted path to the offending field, e.g. `embeds.0.description`."""
    code: str
    message: str


def flatten_errors(raw: msgspec.Raw) -> tuple[FieldError, ...]:
    """Flatten Discord's nested error tree into one `FieldError` per problem.

    Malformed trees are skipped rather than raised: the status and top-level message still describe
    the failure, and an error while reporting an error helps nobody.
    """
    try:
        tree = msgspec.json.decode(raw, type=object)
    except msgspec.DecodeError:
        return ()
    found: list[FieldError] = []
    _walk(tree, (), found)
    return tuple(found)


def _is_object_map(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _walk(node: object, path: tuple[str, ...], found: list[FieldError]) -> None:
    if not _is_object_map(node):
        return
    for key, child in node.items():
        if key == "_errors" and _is_object_list(child):
            for item in child:
                if _is_object_map(item):
                    code = item.get("code", "")
                    message = item.get("message", "")
                    found.append(FieldError(".".join(path), str(code), str(message)))
        else:
            _walk(child, (*path, key), found)


class HTTPError(ShoalError):
    """Discord answered with an error status.

    Attributes:
        status: The HTTP status code.
        code: Discord's JSON error code, when the body had one.
        message: Discord's error message, or the raw body when it was not JSON.
        field_errors: Per-field validation errors (usually for 400 Invalid Form Body).
        route: The request that failed.
    """

    def __init__(
        self,
        route: CompiledRoute,
        status: int,
        message: str,
        code: JSONErrorCode | None = None,
        field_errors: tuple[FieldError, ...] = (),
    ) -> None:
        """Create the error from the parts of a failed response."""
        detail = f" (code {int(code)})" if code is not None else ""
        super().__init__(f"{route.method} {route.path} -> {status}{detail}: {message}")
        self.route: CompiledRoute = route
        self.status: int = status
        self.code: JSONErrorCode | None = code
        self.message: str = message
        self.field_errors: tuple[FieldError, ...] = field_errors

    @classmethod
    def from_response(cls, route: CompiledRoute, status: int, body: bytes) -> "HTTPError":
        """Build the most specific subclass for `status` from the response body."""
        error_type = _STATUS_ERRORS.get(
            status, ServerError if status >= HTTPStatus.INTERNAL_SERVER_ERROR else HTTPError
        )
        try:
            parsed = msgspec.json.decode(body, type=ErrorResponse)
        except (msgspec.DecodeError, msgspec.ValidationError):
            text = body.decode("utf-8", errors="replace").strip() or "no response body"
            return error_type(route, status, text[:500])
        fields = flatten_errors(parsed.errors) if isinstance(parsed.errors, msgspec.Raw) else ()
        return error_type(route, status, parsed.message, parsed.code, fields)


class BadRequestError(HTTPError):
    """400: the request was malformed. See `field_errors`."""


class UnauthorizedError(HTTPError):
    """401: the token is missing or invalid."""


class ForbiddenError(HTTPError):
    """403: the token lacks permission for this resource."""


class NotFoundError(HTTPError):
    """404: the resource does not exist."""


class ServerError(HTTPError):
    """5xx: Discord failed. Idempotent requests were already retried before this was raised."""


class RateLimitedError(HTTPError):
    """429 that Shoal would not wait out: the wait exceeded `max_rate_limit_wait` or retries ran out."""


_STATUS_ERRORS: dict[int, type[HTTPError]] = {
    HTTPStatus.BAD_REQUEST: BadRequestError,
    HTTPStatus.UNAUTHORIZED: UnauthorizedError,
    HTTPStatus.FORBIDDEN: ForbiddenError,
    HTTPStatus.NOT_FOUND: NotFoundError,
    HTTPStatus.TOO_MANY_REQUESTS: RateLimitedError,
}


class TokenInvalidatedError(ShoalError):
    """The client saw a 401 earlier and now refuses every request.

    Discord bans IPs that keep sending invalid requests, and a revoked token turns every request into
    one. Create a new client with a valid token to continue.

    Discord: https://docs.discord.com/developers/topics/rate-limits#invalid-request-limit-aka-cloudflare-bans
    """

    def __init__(self) -> None:
        """Explain why requests are refused."""
        super().__init__("the token was rejected with 401; the client refuses further requests")


class SearchIndexNotReadyError(ShoalError):
    """Discord is still indexing the guild for search and the retries ran out.

    Discord: https://docs.discord.com/developers/resources/message#search-guild-messages
    """

    def __init__(self, documents_indexed: int, retry_after: float) -> None:
        """Report how far indexing got and when Discord suggests trying again."""
        super().__init__(
            f"guild search index is not ready ({documents_indexed} documents indexed); "
            f"retry in {retry_after:.1f}s"
        )
        self.documents_indexed: int = documents_indexed
        self.retry_after: float = retry_after


class ClientClosedError(ShoalError):
    """The client was closed and cannot send more requests."""

    def __init__(self) -> None:
        """Explain why requests are refused."""
        super().__init__("the REST client is closed")
