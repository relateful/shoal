import msgspec
import pytest

from shoal.payloads import JSONErrorCode
from shoal.rest import endpoints
from shoal.rest.errors import (
    BadRequestError,
    ForbiddenError,
    HTTPError,
    NotFoundError,
    RateLimitedError,
    ServerError,
    UnauthorizedError,
    flatten_errors,
)


def test_flatten_errors_walks_the_nested_tree() -> None:
    raw = msgspec.Raw(
        b'{"embeds":{"0":{"description":{"_errors":[{"code":"BASE_TYPE_MAX_LENGTH","message":"too long"}]}}},'
        b'"content":{"_errors":[{"code":"A","message":"b"},"junk"]}}'
    )
    errors = flatten_errors(raw)
    assert [(error.path, error.code) for error in errors] == [
        ("embeds.0.description", "BASE_TYPE_MAX_LENGTH"),
        ("content", "A"),
    ]
    assert flatten_errors(msgspec.Raw(b"not json")) == ()
    assert flatten_errors(msgspec.Raw(b"[1,2]")) == ()


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, BadRequestError),
        (401, UnauthorizedError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (429, RateLimitedError),
        (500, ServerError),
        (524, ServerError),
        (418, HTTPError),
    ],
)
def test_status_maps_to_the_most_specific_error(status: int, error_type: type[HTTPError]) -> None:
    compiled = endpoints.GET_USER.compile(user_id=1)
    error = HTTPError.from_response(compiled, status, b'{"code":50013,"message":"Missing Permissions"}')
    assert type(error) is error_type
    assert error.code is JSONErrorCode.MISSING_PERMISSIONS
    assert error.status == status
    assert "50013" in str(error)


def test_non_json_error_bodies_are_kept_as_text() -> None:
    compiled = endpoints.GET_USER.compile(user_id=1)
    error = HTTPError.from_response(compiled, 502, b"<html>bad gateway</html>")
    assert error.code is None
    assert error.message == "<html>bad gateway</html>"
    assert HTTPError.from_response(compiled, 502, b"").message == "no response body"


def test_an_error_tree_nested_too_deeply_is_skipped() -> None:
    deep = b'{"a":' * 20_000 + b"1" + b"}" * 20_000
    assert flatten_errors(msgspec.Raw(deep)) == ()
