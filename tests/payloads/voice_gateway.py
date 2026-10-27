import msgspec

from shoal.core.codec import decode_json, encode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads.voice_gateway import (
    EncryptionMode,
    SessionDescription,
    Speaking,
    SpeakingFlags,
    VoiceCloseCode,
    VoiceIdentify,
    VoiceOpcode,
    VoicePayload,
    VoiceReady,
)


def test_close_codes_say_whether_to_stop() -> None:
    assert VoiceCloseCode.DISCONNECTED.ends_connection
    assert VoiceCloseCode.DISCONNECTED_CALL_TERMINATED.ends_connection
    assert not VoiceCloseCode.SESSION_TIMEOUT.ends_connection
    assert VoiceCloseCode(4999).name == "UNKNOWN_4999"


def test_the_documented_examples_decode() -> None:
    # Discord's examples, with the encryption modes of the current table.
    ready = decode_json(
        b'{"ssrc":1,"ip":"127.0.0.1","port":1234,"modes":["aead_aes256_gcm_rtpsize","aead_xchacha20_poly1305_rtpsize",'
        b'"xsalsa20_poly1305_lite_rtpsize"],"heartbeat_interval":1}',
        VoiceReady,
    )
    assert ready.modes[0] is EncryptionMode.AEAD_AES256_GCM_RTPSIZE
    assert ready.modes[2].name == "UNKNOWN_XSALSA20_POLY1305_LITE_RTPSIZE"
    message = decode_json(b'{"op":5,"d":{"speaking":0,"delay":0,"ssrc":110},"seq":10}', VoicePayload)
    assert (message.op, message.seq) == (VoiceOpcode.SPEAKING, 10)
    speaking = decode_json(message.d, Speaking)
    assert (speaking.speaking, speaking.ssrc) == (SpeakingFlags(0), 110)
    described = decode_json(
        b'{"mode":"aead_aes256_gcm_rtpsize","secret_key":[251,100,11],"dave_protocol_version":1}',
        SessionDescription,
    )
    assert described.dave_protocol_version == 1
    assert "251" not in repr(described)


def test_identify_hides_its_token() -> None:
    identify = VoiceIdentify(
        server_id=Snowflake(1),
        user_id=Snowflake(2),
        session_id="s",
        token="secret",
        max_dave_protocol_version=1,
    )
    assert "secret" not in repr(identify)
    assert msgspec.json.decode(encode_json(identify))["token"] == "secret"
