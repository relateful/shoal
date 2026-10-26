"""Discord's HTTP API: a standalone client, typed routes and rate limiting.

Usable without a gateway or cache, so bots, workers and dashboard backends share the same client.
Discord-documented rate limit constants are exported from `shoal.payloads`; Shoal's own defaults live
in `shoal.rest.defaults`.

Discord: https://docs.discord.com/developers/reference#http-api
"""

from shoal.rest import defaults, endpoints, resources
from shoal.rest.client import RestClient, Token, TokenType
from shoal.rest.errors import (
    BadRequestError,
    ClientClosedError,
    FieldError,
    ForbiddenError,
    HTTPError,
    NotFoundError,
    RateLimitedError,
    SearchIndexNotReadyError,
    ServerError,
    TokenInvalidatedError,
    UnauthorizedError,
    flatten_errors,
)
from shoal.rest.files import File
from shoal.rest.ratelimit import InvalidRequestGuard, LocalRateLimiter, RateLimiter, RateLimitHeaders
from shoal.rest.requester import QueryScalar, QueryValue, Requester
from shoal.rest.resources.message import ReactionEmoji, reaction_emoji
from shoal.rest.route import CompiledRoute, HTTPMethod, Route
from shoal.rest.transport import AiohttpTransport, HTTPResponse, HTTPTransport, TransportError

__all__ = [
    "AiohttpTransport",
    "BadRequestError",
    "ClientClosedError",
    "CompiledRoute",
    "FieldError",
    "File",
    "ForbiddenError",
    "HTTPError",
    "HTTPMethod",
    "HTTPResponse",
    "HTTPTransport",
    "InvalidRequestGuard",
    "LocalRateLimiter",
    "NotFoundError",
    "QueryScalar",
    "QueryValue",
    "RateLimitHeaders",
    "RateLimitedError",
    "RateLimiter",
    "ReactionEmoji",
    "Requester",
    "RestClient",
    "Route",
    "SearchIndexNotReadyError",
    "ServerError",
    "Token",
    "TokenInvalidatedError",
    "TokenType",
    "TransportError",
    "UnauthorizedError",
    "defaults",
    "endpoints",
    "flatten_errors",
    "reaction_emoji",
    "resources",
]
