import asyncio
import contextlib
import logging

import pytest

from shoal.core.metrics import VOICE_PACKETS_DROPPED, InMemoryMetrics
from shoal.gateway.connection import MessageKind, WebSocketMessage
from shoal.payloads.voice_gateway import EncryptionMode
from shoal.voice.connection import VoiceConnection, VoiceConnectionClosedError
from shoal.voice.crypto import TransportCipher
from shoal.voice.defaults import RECEIVED_PACKETS_QUEUE_SIZE
from shoal.voice.rtp import rtp_header
from tests.support.fakes import ManualClock, settle
from tests.support.voice import (
    EXTERNAL,
    KEY,
    SERVER,
    SSRC,
    FakeVoiceConnector,
    FakeVoiceGateway,
    FakeVoiceTransports,
)

FRAME = bytes([0xFC, 0x01, 0x02, 0x03])
"""A 20 ms Opus packet (CELT, code 0)."""


async def connected(
    *gateways: FakeVoiceGateway, clock: ManualClock | None = None
) -> tuple[VoiceConnection, FakeVoiceConnector, FakeVoiceTransports]:
    connector, transports = FakeVoiceConnector(*gateways), FakeVoiceTransports()
    connection = VoiceConnection(
        SERVER, user_id=1, connector=connector, transports=transports, clock=clock or ManualClock()
    )
    await connection.connect()
    return connection, connector, transports


async def test_the_handshake_follows_discords_order() -> None:
    connection, connector, transports = await connected()
    gateway = connector.opened[0]
    assert connector.urls == ["wss://voice.test:443/?v=8"]
    identify, select = gateway.sent[0], gateway.sent[1]
    assert identify == {
        "op": 0,
        "d": {
            "server_id": "10",
            "user_id": "1",
            "session_id": "voice-session",
            "token": "voice-token",
            "max_dave_protocol_version": 1,
        },
    }
    # IP discovery went to the address from Ready, and its answer to Select Protocol.
    assert transports.addresses == [("198.51.100.1", 50000)]
    assert select == {
        "op": 1,
        "d": {
            "protocol": "udp",
            "data": {"address": EXTERNAL[0], "port": EXTERNAL[1], "mode": "aead_aes256_gcm_rtpsize"},
        },
    }
    assert connection.is_connected
    assert connection.ssrc == SSRC
    assert connection.server is SERVER
    assert "voice-token" not in repr(SERVER)
    await connection.close()
    assert gateway.close_codes == [1000]
    assert transports.transports[0].closed
    assert await connection.closed is None


async def test_frames_go_out_sealed_numbered_and_timed() -> None:
    connection, connector, transports = await connected()
    await connection.speak()
    assert connector.opened[0].sent[-1] == {"op": 5, "d": {"speaking": 1, "ssrc": SSRC, "delay": 0}}
    connection.send_frame(FRAME)
    connection.send_frame(FRAME)
    opener = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    first, second = (opener.unseal(packet) for packet in transports.transports[0].audio())
    assert (first[0].sequence, first[0].timestamp, first[0].ssrc) == (0, 0, SSRC)
    assert (second[0].sequence, second[0].timestamp) == (1, 960)
    assert first[1] == FRAME  # DAVE version 0: not end-to-end encrypted
    await connection.close()
    with pytest.raises(VoiceConnectionClosedError, match="not connected"):
        connection.send_frame(FRAME)


async def test_xchacha_is_used_when_aes_is_not_offered() -> None:
    connection, _, transports = await connected(FakeVoiceGateway(modes=["aead_xchacha20_poly1305_rtpsize"]))
    connection.send_frame(FRAME)
    opener = TransportCipher(EncryptionMode.AEAD_XCHACHA20_POLY1305_RTPSIZE, KEY)
    assert opener.unseal(transports.transports[0].audio()[0])[1] == FRAME
    await connection.close()


async def test_a_server_without_a_supported_mode_is_refused() -> None:
    with pytest.raises(VoiceConnectionClosedError, match="no encryption mode"):
        await connected(FakeVoiceGateway(modes=["xsalsa20_poly1305"]))


async def test_a_close_during_the_handshake_fails_it() -> None:
    gateway = FakeVoiceGateway()
    gateway.drop(4004)
    with pytest.raises(VoiceConnectionClosedError) as closed:
        await connected(gateway)
    assert closed.value.code == 4004
    assert closed.value.ends_connection


async def test_heartbeats_acknowledge_the_last_numbered_message() -> None:
    clock = ManualClock()
    connection, connector, _ = await connected(clock=clock)
    gateway = connector.opened[0]
    gateway.push(5, {"speaking": 0, "ssrc": 110, "user_id": "5"}, seq=10)
    await settle()
    await clock.advance(41.25)
    assert gateway.sent[-1]["op"] == 3
    beat = gateway.sent[-1]["d"]
    assert isinstance(beat, dict)
    assert beat["seq_ack"] == 10
    await settle()
    assert connection.latency is not None
    await connection.close()


async def test_a_dropped_socket_is_resumed_with_what_was_received() -> None:
    clock = ManualClock()
    connection, connector, _ = await connected(clock=clock)
    first = connector.opened[0]
    first.push(5, {"speaking": 0, "ssrc": 110, "user_id": "5"}, seq=12)
    await settle()
    first.drop(None)
    await settle()
    assert len(connector.opened) == 2
    resume = connector.opened[1].sent[0]
    assert resume == {
        "op": 7,
        "d": {"server_id": "10", "session_id": "voice-session", "token": "voice-token", "seq_ack": 12},
    }
    assert connection.is_connected
    await connection.close()


async def test_unanswered_heartbeats_close_the_socket_and_resume() -> None:
    clock = ManualClock()
    connection, connector, _ = await connected(FakeVoiceGateway(acknowledge=False), clock=clock)
    for _ in range(3):
        await clock.advance(41.25)
    await settle()
    assert connector.opened[0].close_codes == [4000]
    assert len(connector.opened) == 2
    assert connection.is_connected
    await connection.close()


@pytest.mark.parametrize(("code", "ends"), [(4014, True), (4022, True), (4006, False)])
async def test_a_close_that_ends_the_session_ends_the_connection(code: int, ends: bool) -> None:
    connection, connector, transports = await connected()
    connector.opened[0].drop(code)
    ended = await asyncio.wait_for(connection.closed, timeout=2)
    assert ended is not None
    assert ended.code == code
    assert ended.ends_connection is ends
    assert not connection.is_connected
    assert transports.transports[0].closed


async def test_resuming_gives_up_after_repeated_failures(caplog: pytest.LogCaptureFixture) -> None:
    clock = ManualClock()
    failing = [FakeVoiceGateway() for _ in range(6)]
    for gateway in failing:
        gateway.drop(None)
    connection, connector, _ = await connected(FakeVoiceGateway(), *failing, clock=clock)
    with caplog.at_level(logging.WARNING, logger="shoal.voice"):
        connector.opened[0].drop(None)
        for _ in range(10):
            await settle()
            await clock.advance(60)
    ended = await asyncio.wait_for(connection.closed, timeout=2)
    assert ended is not None
    assert "could not be resumed" in str(ended)


async def test_received_audio_says_who_sent_it() -> None:
    connection, connector, transports = await connected()
    gateway, socket = connector.opened[0], transports.transports[0]
    gateway.push(5, {"speaking": 1, "ssrc": 55, "user_id": "99"}, seq=1)
    gateway.push(11, {"user_ids": ["99"]})
    await settle()
    sender = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    received = connection.packets()
    first = asyncio.ensure_future(anext(received))
    await settle()
    socket.incoming.put_nowait(b"\x81\xc8" + bytes(30))  # RTCP: skipped
    socket.incoming.put_nowait(sender.seal(rtp_header(3, 960, 55), FRAME)[:-1] + b"\xff")  # bad seal
    socket.incoming.put_nowait(sender.seal(rtp_header(4, 1920, 77), FRAME))  # unknown sender
    socket.incoming.put_nowait(sender.seal(rtp_header(5, 2880, 55), FRAME))
    packet = await asyncio.wait_for(first, timeout=2)
    assert (packet.user_id, packet.ssrc, packet.sequence, packet.timestamp, packet.opus) == (
        99,
        55,
        5,
        2880,
        FRAME,
    )
    gateway.push(13, {"user_id": "99"})
    await settle()
    await connection.close()
    with contextlib.suppress(StopAsyncIteration):
        await asyncio.wait_for(anext(received), timeout=2)


async def test_dave_starts_with_a_key_package_when_the_call_is_encrypted() -> None:
    connection, connector, _ = await connected(FakeVoiceGateway(dave_version=1))
    assert connector.opened[0].sent_binary[0][0] == 26  # DAVE MLS Key Package
    assert connection.dave.protocol_version == 1
    assert not connection.dave.ready  # no group yet: frames go out as they are
    await connection.close()


async def test_garbage_from_the_gateway_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    connection, connector, _ = await connected()
    gateway = connector.opened[0]
    with caplog.at_level(logging.WARNING, logger="shoal.voice"):
        gateway.incoming.put_nowait(WebSocketMessage(MessageKind.TEXT, b"{not json"))
        gateway.incoming.put_nowait(WebSocketMessage(MessageKind.BINARY, b"\0"))
        await settle()
    assert "could not be handled" in caplog.text
    assert connection.is_connected
    await connection.close()


async def test_a_cancelled_connect_closes_what_it_opened() -> None:
    connector, transports = FakeVoiceConnector(), FakeVoiceTransports(discovers=False)
    connection = VoiceConnection(
        SERVER, user_id=1, connector=connector, transports=transports, clock=ManualClock()
    )
    connecting = asyncio.ensure_future(connection.connect())
    await settle()
    assert transports.transports  # waiting on IP discovery
    connecting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await connecting
    assert connector.opened[0].close_codes == [1000]
    assert transports.transports[0].closed
    assert await connection.closed is None


async def test_every_close_waits_for_the_same_one() -> None:
    connection, connector, transports = await connected()
    first = asyncio.ensure_future(connection.close())
    await connection.close()
    assert transports.transports[0].closed
    assert connector.opened[0].close_codes == [1000]
    assert connection.closed.done()
    await first


async def test_resuming_closes_the_socket_it_replaces() -> None:
    connection, connector, _ = await connected()
    connector.opened[0].drop(None)
    await settle()
    assert connector.opened[0].close_codes == [4000]
    assert connection.is_connected
    await connection.close()
    assert connector.opened[1].close_codes == [1000]


async def test_a_resume_left_unanswered_is_given_up_and_tried_again() -> None:
    clock = ManualClock()
    silent = FakeVoiceGateway(resumes=False)
    connection, connector, _ = await connected(FakeVoiceGateway(), silent, clock=clock)
    connector.opened[0].drop(None)
    await settle()
    assert len(connector.opened) == 2
    await clock.advance(30)  # JOIN_TIMEOUT
    await settle()
    assert silent.close_codes == [4000]
    await clock.advance(1)  # the second attempt's backoff
    await settle()
    assert len(connector.opened) == 3
    assert connection.is_connected
    await connection.close()


async def test_a_session_lost_again_at_once_backs_off_and_a_stable_one_does_not() -> None:
    clock = ManualClock()
    connection, connector, _ = await connected(clock=clock)
    connector.opened[0].drop(4015)
    await settle()
    assert len(connector.opened) == 2  # the first resume goes at once
    connector.opened[1].drop(4015)
    await settle()
    assert len(connector.opened) == 2  # the second waits
    await clock.advance(1)
    await settle()
    assert len(connector.opened) == 3
    await clock.advance(60)  # STABLE_SESSION: the count starts over
    connector.opened[2].drop(4015)
    await settle()
    assert len(connector.opened) == 4
    await connection.close()


async def test_every_listener_gets_every_packet_and_drops_are_counted() -> None:
    metrics = InMemoryMetrics()
    connector, transports = FakeVoiceConnector(), FakeVoiceTransports()
    connection = VoiceConnection(
        SERVER, user_id=1, connector=connector, transports=transports, metrics=metrics, clock=ManualClock()
    )
    await connection.connect()
    connector.opened[0].push(5, {"speaking": 1, "ssrc": 55, "user_id": "99"}, seq=1)
    await settle()
    first, second = connection.packets(), connection.packets()
    waiting = [asyncio.ensure_future(anext(first)), asyncio.ensure_future(anext(second))]
    await settle()
    sender = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    socket = transports.transports[0]
    socket.incoming.put_nowait(sender.seal(rtp_header(1, 0, 55), FRAME)[:-1] + b"\xff")
    socket.incoming.put_nowait(sender.seal(rtp_header(2, 960, 77), FRAME))
    for sequence in range(3, 3 + RECEIVED_PACKETS_QUEUE_SIZE + 2):
        socket.incoming.put_nowait(sender.seal(rtp_header(sequence, 0, 55), FRAME))
    received = await asyncio.wait_for(asyncio.gather(*waiting), timeout=2)
    # Two packets more than a listener holds arrived before either read: each lost the oldest two.
    assert [packet.sequence for packet in received] == [5, 5]
    dropped = VOICE_PACKETS_DROPPED
    assert metrics.counters[InMemoryMetrics.key(dropped, {"reason": "unsealed"})] == 1
    assert metrics.counters[InMemoryMetrics.key(dropped, {"reason": "undecrypted"})] == 1
    assert metrics.counters[InMemoryMetrics.key(dropped, {"reason": "behind"})] == 4
    await connection.close()
    # Each listener reads what is left, then its iteration ends with the connection.
    for listener in (first, second):
        assert len([packet async for packet in listener]) == RECEIVED_PACKETS_QUEUE_SIZE - 1


async def test_an_invalid_frame_sends_nothing() -> None:
    connection, _, transports = await connected()
    with pytest.raises(ValueError, match="TOC byte"):
        connection.send_frame(b"")
    connection.send_frame(FRAME)
    assert len(transports.transports[0].audio()) == 1
    opener = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    assert opener.unseal(transports.transports[0].audio()[0])[0].sequence == 0
    await connection.close()


async def test_dave_messages_reach_the_session() -> None:
    clock = ManualClock()
    connection, connector, _ = await connected(FakeVoiceGateway(dave_version=1), clock=clock)
    gateway = connector.opened[0]
    gateway.push(21, {"transition_id": 5, "protocol_version": 0})
    gateway.push_binary(40, 25, b"external sender")
    await settle()
    assert {"op": 23, "d": {"transition_id": 5}} in gateway.sent
    await clock.advance(41.25)
    beat = gateway.sent[-1]["d"]
    assert isinstance(beat, dict)
    assert beat["seq_ack"] == 40  # binary messages are numbered too
    await connection.close()
