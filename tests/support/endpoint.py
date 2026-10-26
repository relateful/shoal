"""Posting signed interactions to an `Endpoint`, as Discord does."""

import aiohttp
import msgspec

from shoal.core.codec import JSONObject
from shoal.endpoint import Endpoint
from tests.support.signing import sign


async def post(url: str, payload: JSONObject, *, signature: str | None = None) -> tuple[int, bytes]:
    """POST `payload` signed with the test key (or with `signature`); the status and body."""
    timestamp = "1700000000"
    body = msgspec.json.encode(payload)
    headers = {
        "X-Signature-Ed25519": signature if signature is not None else sign(timestamp, body),
        "X-Signature-Timestamp": timestamp,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session, session.post(url, data=body, headers=headers) as response:
        return response.status, await response.read()


def url_of(server: Endpoint) -> str:
    """Where a started endpoint listens."""
    host, port = server.address
    return f"http://{host}:{port}/interactions"
