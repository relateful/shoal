import asyncio

import pytest
from aiohttp import WSMsgType, web

from shoal.gateway.connection import AiohttpGatewayConnector, MessageKind
from tests.support.server import free_port, serve


async def test_text_binary_send_and_close_code_round_trip() -> None:
    close_codes: list[int | None] = []
    received: list[str] = []

    async def gateway(request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        await socket.send_str('{"op":10}')
        await socket.send_bytes(b"\x00\x01")
        received.extend([message.data async for message in socket if message.type is WSMsgType.TEXT])
        close_codes.append(socket.close_code)
        return socket

    app = web.Application()
    app.router.add_get("/", gateway)
    async with serve(app) as address:
        connector = AiohttpGatewayConnector()
        connection = await connector.connect(f"ws://{address}/?v=10")
        first = await connection.receive()
        second = await connection.receive()
        await connection.send(b'{"op":1,"d":null}')
        await connection.close(4900)
        closed = await connection.receive()
        await connector.close()
        await asyncio.sleep(0.05)
    assert (first.kind, first.data) == (MessageKind.TEXT, b'{"op":10}')
    assert (second.kind, second.data) == (MessageKind.BINARY, b"\x00\x01")
    assert closed.kind is MessageKind.CLOSED
    assert received == ['{"op":1,"d":null}']
    assert close_codes == [4900]


async def test_server_close_reports_the_close_code() -> None:
    async def gateway(request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        await socket.close(code=4004)
        return socket

    app = web.Application()
    app.router.add_get("/", gateway)
    async with serve(app) as address:
        connector = AiohttpGatewayConnector()
        connection = await connector.connect(f"ws://{address}/")
        message = await connection.receive()
        await connector.close()
    assert message.kind is MessageKind.CLOSED
    assert message.close_code == 4004


async def test_handshake_failures_raise_connection_errors() -> None:
    async def unavailable(request: web.Request) -> web.Response:
        del request
        return web.Response(status=503)

    app = web.Application()
    app.router.add_get("/", unavailable)
    async with serve(app) as address:
        connector = AiohttpGatewayConnector()
        with pytest.raises(ConnectionError, match="could not connect"):
            await connector.connect(f"ws://{address}/")
        await connector.close()
    connector = AiohttpGatewayConnector(connect_timeout=2)
    with pytest.raises(ConnectionError):
        await connector.connect(f"ws://127.0.0.1:{free_port()}/")
    await connector.close()
