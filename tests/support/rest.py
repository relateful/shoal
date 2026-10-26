"""Checking `RestClient` endpoint methods against what Discord expects, one table row per call.

Each resource's test module lists `EndpointCase`s: the call, the request it must send, and a response
Discord could give. `check_endpoint` runs one against a fake transport and also re-encodes what the
client returned, which must give back the response: nothing dropped, renamed or mistyped.
"""

import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Final

import msgspec
import pytest

from shoal.core.codec import encode_json
from shoal.core.metrics import REST_REQUESTS, InMemoryMetrics
from shoal.rest.client import RestClient, Token
from shoal.rest.ratelimit import LocalRateLimiter
from tests.support.fakes import FakeClock, FakeTransport
from tests.support.multipart import FormPart, parse_form

API = "https://discord.com/api/v10"

type Call = Callable[[RestClient], Awaitable[object]]

SAME_AS_RESPONSE: Final = object()
"""The default `EndpointCase.result`: the method returns the response as Discord sent it."""


@dataclass(frozen=True, slots=True)
class EndpointCase:
    """One endpoint call and the request it must produce.

    `path` is relative to the versioned API base and includes any query string. `response` is the
    JSON Discord answers with; `None` means an empty `204`.
    """

    name: str
    call: Call
    method: str
    path: str
    body: object = None
    response: object = None
    reason: str | None = None
    """The `X-Audit-Log-Reason` header the call must send."""
    files: tuple[FormPart, ...] = ()
    """The file parts of a `multipart/form-data` request; `body` is then its `payload_json` part."""
    result: object = SAME_AS_RESPONSE
    """What the returned value encodes to, when the method unwraps the response (`{"items": [...]}`)."""


def make_client(
    transport: FakeTransport, *, token: Token | None = None, metrics: InMemoryMetrics | None = None
) -> RestClient:
    clock = FakeClock()
    return RestClient(
        token or Token.bot("secret"),
        transport=transport,
        rate_limiter=LocalRateLimiter(clock=clock, global_per_second=None),
        clock=clock,
        metrics=metrics,
        random_source=random.Random(0),
    )


def endpoint_cases(cases: Sequence[EndpointCase]) -> pytest.MarkDecorator:
    """Parametrize a test over `cases`, named after each case."""
    return pytest.mark.parametrize("case", cases, ids=[case.name for case in cases])


async def check_endpoint(case: EndpointCase) -> str:
    """Run `case` and check the request and the decoded result. Returns the route template used."""
    transport = FakeTransport()
    transport.queue(204 if case.response is None else 200, case.response)
    metrics = InMemoryMetrics()
    result = await case.call(make_client(transport, metrics=metrics))
    [request] = transport.requests
    assert (request.method, request.url) == (case.method, f"{API}{case.path}")
    sent: object = None
    files: tuple[FormPart, ...] = ()
    if case.files:
        parts = parse_form(request.body or b"", request.headers["Content-Type"])
        if parts[0].name == "payload_json":
            sent = msgspec.json.decode(parts.pop(0).data)
        files = tuple(parts)
    elif request.body is not None:
        sent = msgspec.json.decode(request.body)
    assert sent == case.body
    assert files == case.files
    assert request.headers.get("X-Audit-Log-Reason") == case.reason
    response: object = case.response if case.result is SAME_AS_RESPONSE else case.result
    if response is None:
        assert result is None
    else:
        # The one allowed difference: UTC times come back as `Z` rather than Discord's `+00:00`.
        expected = msgspec.json.encode(response).replace(b"+00:00", b"Z")
        assert msgspec.json.decode(encode_json(result)) == msgspec.json.decode(expected)
    [series] = [key for key in metrics.counters if key[0] == REST_REQUESTS.name]
    return dict(series[1])["route"]
