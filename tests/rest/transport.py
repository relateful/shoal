import msgspec
import pytest
from aiohttp import web

from shoal.rest.transport import AiohttpTransport, TransportError
from tests.support.server import free_port, serve


async def echo(request: web.Request) -> web.Response:
    body = await request.read()
    payload = {"method": request.method, "auth": request.headers.get("Authorization"), "body": body.decode()}
    return web.json_response(payload, status=418, headers={"X-RateLimit-Bucket": "abc"})


async def test_sends_the_request_and_returns_the_raw_response() -> None:
    app = web.Application()
    app.router.add_route("*", "/echo", echo)
    async with serve(app) as address:
        transport = AiohttpTransport()
        response = await transport.request(
            "POST", f"http://{address}/echo", headers={"Authorization": "Bot x"}, body=b'{"a":1}'
        )
        await transport.close()
        await transport.close()
    assert response.status == 418
    assert response.headers["x-ratelimit-bucket"] == "abc"
    assert msgspec.json.decode(response.body) == {"method": "POST", "auth": "Bot x", "body": '{"a":1}'}


async def test_connection_failures_become_transport_errors() -> None:
    transport = AiohttpTransport(timeout=2)
    with pytest.raises(TransportError) as raised:
        await transport.request(
            "GET",
            f"http://127.0.0.1:{free_port()}/webhooks/1/TOKEN/messages?content=secret",
            headers={},
            body=None,
        )
    await transport.close()
    message = str(raised.value)
    assert message.startswith("GET request failed")
    assert "secret" not in message
    assert "TOKEN" not in message


def test_transport_errors_are_os_errors_so_the_client_retries_them() -> None:
    assert issubclass(TransportError, OSError)
