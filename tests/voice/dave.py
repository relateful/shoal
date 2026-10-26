import logging
import struct

import davey
import msgspec
import pytest

from shoal.payloads.voice_gateway import SILENCE_FRAME, VoiceOpcode
from shoal.voice.dave import Dave


class Recorder:
    def __init__(self) -> None:
        self.json: list[tuple[VoiceOpcode, dict[str, object]]] = []
        self.binary: list[tuple[VoiceOpcode, bytes]] = []

    async def send_json(self, opcode: VoiceOpcode, data: msgspec.Struct) -> None:
        self.json.append((opcode, msgspec.to_builtins(data)))

    async def send_binary(self, opcode: VoiceOpcode, payload: bytes) -> None:
        self.binary.append((opcode, payload))


def dave() -> tuple[Dave, Recorder]:
    sent = Recorder()
    return Dave(user_id=1, channel_id=20, send_json=sent.send_json, send_binary=sent.send_binary), sent


def raw(data: object) -> msgspec.Raw:
    return msgspec.Raw(msgspec.json.encode(data))


def external_sender() -> bytes:
    """A serialized MLS external sender: a P-256 signature key and a basic credential."""
    key = davey.generate_p256_keypair().public
    identity = b"voice-gateway"
    return (
        struct.pack(">H", 0x4000 | len(key)) + key + struct.pack(">H", 1) + bytes([len(identity)]) + identity
    )


async def test_an_unencrypted_call_passes_frames_as_they_are() -> None:
    state, sent = dave()
    await state.start(0)
    assert (state.protocol_version, state.ready, state.privacy_code) == (0, False, None)
    assert sent.binary == []
    assert state.encrypt(b"\xfc\x01") == b"\xfc\x01"
    assert state.decrypt(5, b"\xfc\x01") == b"\xfc\x01"


async def test_an_encrypted_call_starts_with_a_key_package() -> None:
    state, sent = dave()
    await state.handle_binary(VoiceOpcode.DAVE_MLS_EXTERNAL_SENDER, external_sender())
    await state.start(1)
    assert [opcode for opcode, _ in sent.binary] == [VoiceOpcode.DAVE_MLS_KEY_PACKAGE]
    assert len(sent.binary[0][1]) > 100
    assert not state.ready  # no group yet
    # Until the group exists, frames go out as they are and received ones cannot be read.
    assert state.encrypt(b"\xfc\x01") == b"\xfc\x01"
    assert state.decrypt(5, b"\xfc\x01") is None
    assert state.decrypt(5, SILENCE_FRAME) == SILENCE_FRAME
    assert state.encrypt(SILENCE_FRAME) == SILENCE_FRAME


async def test_transitions_are_acknowledged_then_executed() -> None:
    state, sent = dave()
    await state.start(1)
    await state.handle(VoiceOpcode.DAVE_PREPARE_TRANSITION, raw({"protocol_version": 0, "transition_id": 5}))
    assert sent.json == [(VoiceOpcode.DAVE_TRANSITION_READY, {"transition_id": 5})]
    assert state.protocol_version == 1  # not before the gateway executes it
    await state.handle(VoiceOpcode.DAVE_EXECUTE_TRANSITION, raw({"transition_id": 4}))
    assert state.protocol_version == 1  # another transition: ignored
    await state.handle(VoiceOpcode.DAVE_PREPARE_TRANSITION, raw({"protocol_version": 0, "transition_id": 5}))
    await state.handle(VoiceOpcode.DAVE_EXECUTE_TRANSITION, raw({"transition_id": 5}))
    assert state.protocol_version == 0
    # Back up: transition 0 executes at once, without an acknowledgement.
    await state.handle(VoiceOpcode.DAVE_PREPARE_TRANSITION, raw({"protocol_version": 1, "transition_id": 0}))
    assert state.protocol_version == 1
    await state.handle(VoiceOpcode.DAVE_PREPARE_TRANSITION, raw({"protocol_version": 1, "transition_id": 6}))
    await state.handle(VoiceOpcode.DAVE_EXECUTE_TRANSITION, raw({"transition_id": 6}))
    assert state.protocol_version == 1


async def test_a_new_group_starts_over_with_a_new_key_package() -> None:
    state, sent = dave()
    await state.start(0)
    await state.handle(VoiceOpcode.DAVE_PREPARE_EPOCH, raw({"protocol_version": 1, "epoch": 2}))
    assert sent.binary == []  # not a new group
    await state.handle(VoiceOpcode.DAVE_PREPARE_EPOCH, raw({"protocol_version": 1, "epoch": 1}))
    assert [opcode for opcode, _ in sent.binary] == [VoiceOpcode.DAVE_MLS_KEY_PACKAGE]
    assert state.protocol_version == 1
    await state.start(0)  # the call stops encrypting: the session is reset, frames pass for a while
    assert not state.ready


async def test_an_unusable_commit_or_welcome_asks_to_be_re_added_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, sent = dave()
    await state.start(1)
    sent.binary.clear()
    with caplog.at_level(logging.WARNING, logger="shoal.voice"):
        await state.handle_binary(VoiceOpcode.DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION, b"\x00\x03not a commit")
        await state.handle_binary(VoiceOpcode.DAVE_MLS_WELCOME, b"\x00\x04not a welcome")
    assert sent.json == [(VoiceOpcode.DAVE_MLS_INVALID_COMMIT_WELCOME, {"transition_id": 3})]
    assert [opcode for opcode, _ in sent.binary] == [VoiceOpcode.DAVE_MLS_KEY_PACKAGE]
    assert "asking to be re-added" in caplog.text
    # A transition executed clears the recovery, so a later failure is reported again.
    await state.handle(VoiceOpcode.DAVE_PREPARE_TRANSITION, raw({"protocol_version": 1, "transition_id": 0}))
    await state.handle_binary(VoiceOpcode.DAVE_MLS_WELCOME, b"\x00\x05not a welcome")
    assert sent.json[-1] == (VoiceOpcode.DAVE_MLS_INVALID_COMMIT_WELCOME, {"transition_id": 5})


async def test_proposals_that_cannot_be_used_are_logged_and_skipped(caplog: pytest.LogCaptureFixture) -> None:
    state, sent = dave()
    await state.handle_binary(VoiceOpcode.DAVE_MLS_PROPOSALS, b"\x00proposals")  # no session yet
    await state.start(1)
    state.users_joined([2, 3])
    state.user_left(3)
    sent.binary.clear()
    with caplog.at_level(logging.ERROR, logger="shoal.voice"):
        await state.handle_binary(VoiceOpcode.DAVE_MLS_PROPOSALS, b"")
        await state.handle_binary(VoiceOpcode.DAVE_MLS_PROPOSALS, b"\x09proposals")
        await state.handle_binary(VoiceOpcode.DAVE_MLS_PROPOSALS, b"\x00not proposals")
        await state.handle_binary(VoiceOpcode.DAVE_MLS_ANNOUNCE_COMMIT_TRANSITION, b"\x00")
    assert "could not process DAVE proposals" in caplog.text
    assert sent.binary == []
