"""HTTP routes and their rate limit identity.

A `Route` is declared once per Discord endpoint with a link to its documentation. Compiling it with
path parameters produces the URL path and the keys the rate limiter buckets on.

Discord: https://docs.discord.com/developers/topics/rate-limits
"""

import re
import string
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final
from urllib.parse import quote

from shoal.payloads.api import DOCS_BASE_URL
from shoal.payloads.rate_limits import MAJOR_PARAMETERS

SECRET_PARAMETERS: Final = frozenset({"interaction_token", "invite_code", "template_code", "webhook_token"})
"""Path parameters that grant access to whoever holds them: tokens post as the app, an invite code
joins its guild, a template code copies one. They never appear in logs, error messages or metric
labels; `CompiledRoute.display` keeps them as placeholders."""

_DOT_SEGMENTS: Final = frozenset({"", ".", ".."})
"""Values that URL normalisation would remove or collapse, sending the request to another route."""

_PARAMETER_NAME: Final = re.compile(r"^[a-z][a-z0-9_]*$")


class HTTPMethod(StrEnum):
    """The HTTP methods Discord's API uses."""

    DELETE = "DELETE"
    GET = "GET"
    PATCH = "PATCH"
    POST = "POST"
    PUT = "PUT"

    @property
    def is_idempotent(self) -> bool:
        """Whether repeating the request cannot create a second effect, so it is safe to retry."""
        return self in {HTTPMethod.GET, HTTPMethod.PUT, HTTPMethod.DELETE}


@dataclass(frozen=True, slots=True)
class Route:
    """One Discord endpoint.

    Args:
        method: The HTTP method.
        path: The path template relative to the versioned base URL, e.g.
            `/channels/{channel_id}/messages`. Placeholders are snake_case.
        docs: The full URL of the endpoint's section in the Discord docs. Required: every route
            must say where its behaviour is specified.
        global_limit: Whether the request counts towards the bot's global rate limit. Interaction
            callbacks do not.

    Raises:
        ValueError: The path or docs link is malformed.
    """

    method: HTTPMethod
    path: str
    docs: str
    global_limit: bool = True
    parameters: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            msg = f"route path must start with '/': {self.path!r}"
            raise ValueError(msg)
        if not self.docs.startswith(DOCS_BASE_URL) or "#" not in self.docs:
            msg = f"route docs must be a {DOCS_BASE_URL}...#anchor link, got {self.docs!r}"
            raise ValueError(msg)
        names: set[str] = set()
        for _, name, spec, conversion in string.Formatter().parse(self.path):
            if name is None:
                continue
            if spec or conversion or not _PARAMETER_NAME.match(name):
                msg = f"invalid placeholder {name!r} in route {self.path!r}"
                raise ValueError(msg)
            names.add(name)
        object.__setattr__(self, "parameters", frozenset(names))

    @property
    def key(self) -> str:
        """The route's identity before Discord tells us its bucket hash: `METHOD /template`."""
        return f"{self.method} {self.path}"

    def compile(self, **values: int | str) -> "CompiledRoute":
        """Fill in the path parameters.

        Raises:
            ValueError: A parameter is missing or unexpected, or is empty, `.` or `..`, which would
                turn the path into another endpoint's (`/reactions/..` is the message itself).
        """
        given = frozenset(values)
        if given != self.parameters:
            missing = sorted(self.parameters - given)
            extra = sorted(given - self.parameters)
            msg = f"route {self.key} parameters mismatch: missing {missing}, unexpected {extra}"
            raise ValueError(msg)
        for name, value in values.items():
            if str(value) in _DOT_SEGMENTS:
                msg = f"route {self.key} parameter {name} cannot be {str(value)!r}"
                raise ValueError(msg)
        encoded = {name: quote(str(value), safe="") for name, value in values.items()}
        shown = {
            name: f"{{{name}}}" if name in SECRET_PARAMETERS else value for name, value in encoded.items()
        }
        major = tuple(f"{name}={values[name]}" for name in sorted(self.parameters & MAJOR_PARAMETERS))
        return CompiledRoute(
            route=self,
            path=self.path.format_map(encoded),
            display=self.path.format_map(shown),
            major=":".join(major),
        )


@dataclass(frozen=True, slots=True)
class CompiledRoute:
    """A route with its parameters filled in."""

    route: Route
    path: str = field(repr=False)
    """The real path. It can hold a token, so it is left out of the repr; log `display` instead."""
    display: str
    """The path for logs and error messages: secret parameters (tokens) stay as placeholders."""
    major: str = field(repr=False)
    """The major parameter values joined into one string, e.g. `channel_id=123`. It can hold a
    token, so it is left out of the repr and never logged."""

    @property
    def method(self) -> HTTPMethod:
        """The HTTP method."""
        return self.route.method
