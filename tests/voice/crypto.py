import pytest
from cryptography.exceptions import InvalidTag

from shoal.payloads.voice_gateway import EncryptionMode
from shoal.voice.crypto import (
    TransportCipher,
    hchacha20,
    xchacha20_poly1305_decrypt,
    xchacha20_poly1305_encrypt,
)
from shoal.voice.rtp import rtp_header

KEY = bytes(range(32))


def test_hchacha20_matches_the_drafts_vector() -> None:
    # draft-irtf-cfrg-xchacha-03, section 2.2.1.
    nonce = bytes.fromhex("000000090000004a0000000031415927")
    expected = "82413b4227b27bfed30e42508a877d73a0f9e4d58a74a853c12ec41326d3ecdc"
    assert hchacha20(KEY, nonce).hex() == expected
    with pytest.raises(ValueError, match="16-byte nonce"):
        hchacha20(KEY, bytes(12))


def test_xchacha20_poly1305_matches_the_drafts_vector() -> None:
    # draft-irtf-cfrg-xchacha-03, appendix A.3.1.
    plaintext = (
        b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, "
        b"sunscreen would be it."
    )
    aad = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
    key = bytes(range(0x80, 0xA0))
    nonce = bytes(range(0x40, 0x58))
    sealed = xchacha20_poly1305_encrypt(key, nonce, plaintext, aad)
    assert sealed[:32].hex() == "bd6d179d3e83d43b9576579493c0e939572a1700252bfaccbed2902c21396cbb"
    assert sealed[-16:].hex() == "c0875924c1c7987947deafd8780acf49"
    assert xchacha20_poly1305_decrypt(key, nonce, sealed, aad) == plaintext


@pytest.mark.parametrize("mode", list(EncryptionMode))
def test_packets_round_trip_with_the_counter_appended(mode: EncryptionMode) -> None:
    sender, receiver = TransportCipher(mode, KEY), TransportCipher(mode, KEY)
    assert sender.mode is mode
    header = rtp_header(1, 960, 7)
    first, second = sender.seal(header, b"opus"), sender.seal(header, b"opus")
    assert first[:12] == header
    assert (first[-4:], second[-4:]) == (b"\x00\x00\x00\x00", b"\x00\x00\x00\x01")
    parsed, payload = receiver.unseal(first)
    assert (parsed.sequence, parsed.timestamp, parsed.ssrc, payload) == (1, 960, 7, b"opus")
    with pytest.raises(InvalidTag):
        receiver.unseal(first[:-5] + bytes([first[-5] ^ 1]) + first[-4:])


def test_a_header_extension_is_stripped_from_the_payload() -> None:
    cipher = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY)
    # Extension bit set; the 4-byte preamble says one word of extension data follows, encrypted.
    header = bytes([0x90]) + rtp_header(2, 0, 9)[1:] + b"\xbe\xde\x00\x01"
    packet = cipher.seal(header, b"\x01\x02\x03\x04" + b"opus")
    parsed, payload = TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY).unseal(packet)
    assert (parsed.size, parsed.extension_size, payload) == (16, 4, b"opus")


def test_keys_and_modes_are_checked() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, bytes(16))
    with pytest.raises(ValueError, match="not supported"):
        TransportCipher(EncryptionMode("xsalsa20_poly1305"), KEY)
    with pytest.raises(ValueError, match="too short"):
        TransportCipher(EncryptionMode.AEAD_AES256_GCM_RTPSIZE, KEY).unseal(rtp_header(0, 0, 0))
