"""Transport encryption of voice packets between the bot and Discord's voice server.

Both modes Discord offers are AEADs over the RTP payload, with the RTP header as additional data and
a 32-bit counter appended to the packet as the nonce (`_rtpsize`: the unencrypted header is the
fixed header, its CSRCs and an extension's 4-byte preamble, as in SRTP).

`aead_xchacha20_poly1305_rtpsize` is XChaCha20-Poly1305: a subkey from HChaCha20 over the first 16
bytes of the 24-byte nonce, then ChaCha20-Poly1305 with the last 8. HChaCha20 is the ChaCha20 block
function without its final addition, so it is recovered from one ChaCha20 keystream block by
subtracting the input words that block added.

Discord: https://docs.discord.com/developers/topics/voice-connections#transport-encryption-modes
XChaCha20: https://datatracker.ietf.org/doc/html/draft-irtf-cfrg-xchacha-03
"""

import struct
from typing import Final, final

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from shoal.payloads.voice_gateway import EncryptionMode
from shoal.voice.rtp import RtpHeader, parse_rtp

_COUNTER_SIZE: Final = 4
"""Bytes of the nonce counter appended to every packet."""

_KEY_SIZE: Final = 32
"""Bytes of the key from Session Description, for both modes."""

_SUPPORTED_MODES: Final = frozenset(
    {EncryptionMode.AEAD_AES256_GCM_RTPSIZE, EncryptionMode.AEAD_XCHACHA20_POLY1305_RTPSIZE}
)
"""The modes this cipher implements; the voice server may offer others."""

_SIGMA: Final = struct.unpack("<4I", b"expand 32-byte k")
"""ChaCha20's constant words, which its keystream block adds back in."""


def hchacha20(key: bytes, nonce: bytes) -> bytes:
    """The HChaCha20 subkey of a 32-byte key and a 16-byte nonce.

    Raises:
        ValueError: The key is not 32 bytes or the nonce not 16.
    """
    if len(key) != _KEY_SIZE or len(nonce) != 16:  # noqa: PLR2004 - HChaCha20's nonce size
        msg = "HChaCha20 takes a 32-byte key and a 16-byte nonce"
        raise ValueError(msg)
    # ChaCha20 here takes the full 16-byte block input (counter and nonce): exactly HChaCha20's.
    block = Cipher(algorithms.ChaCha20(key, nonce), mode=None).encryptor().update(bytes(64))
    words = struct.unpack("<16I", block)
    added = struct.unpack("<4I", nonce)
    first = [(word - constant) & 0xFFFFFFFF for word, constant in zip(words[:4], _SIGMA, strict=True)]
    last = [(word - given) & 0xFFFFFFFF for word, given in zip(words[12:], added, strict=True)]
    return struct.pack("<8I", *first, *last)


def xchacha20_poly1305_encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """XChaCha20-Poly1305 with a 24-byte nonce: the ciphertext and its 16-byte tag."""
    return ChaCha20Poly1305(hchacha20(key, nonce[:16])).encrypt(bytes(4) + nonce[16:], plaintext, aad)


def xchacha20_poly1305_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """The plaintext of XChaCha20-Poly1305 ciphertext.

    Raises:
        cryptography.exceptions.InvalidTag: The packet was not sealed with this key and nonce.
    """
    return ChaCha20Poly1305(hchacha20(key, nonce[:16])).decrypt(bytes(4) + nonce[16:], ciphertext, aad)


@final
class TransportCipher:
    """Seals outgoing voice packets and opens incoming ones, for one session's mode and key.

    Args:
        mode: The mode the session uses.
        key: The 32-byte `secret_key` from Session Description.

    Raises:
        ValueError: The key is not 32 bytes, or the mode is one Shoal does not implement.
    """

    __slots__ = ("_aes", "_counter", "_key", "_mode")

    def __init__(self, mode: EncryptionMode, key: bytes) -> None:
        """Create a cipher; see the class docstring for the arguments."""
        if len(key) != _KEY_SIZE:
            msg = "a voice session key is 32 bytes"
            raise ValueError(msg)
        if mode not in _SUPPORTED_MODES:
            msg = f"voice encryption mode {mode} is not supported"
            raise ValueError(msg)
        self._mode: EncryptionMode = mode
        self._key: bytes = key
        self._aes: AESGCM | None = AESGCM(key) if mode is EncryptionMode.AEAD_AES256_GCM_RTPSIZE else None
        self._counter: int = 0

    @property
    def mode(self) -> EncryptionMode:
        """The mode this cipher seals and opens with."""
        return self._mode

    def _nonce(self, counter: bytes) -> bytes:
        # The counter leads the nonce; the rest is zero (12 bytes for AES-GCM, 24 for XChaCha20).
        return counter + bytes(8 if self._aes is not None else 20)

    def seal(self, header: bytes, payload: bytes) -> bytes:
        """The packet carrying `payload` after `header`: header, ciphertext with tag, counter."""
        counter = self._counter.to_bytes(_COUNTER_SIZE, "big")
        self._counter = (self._counter + 1) & 0xFFFFFFFF
        nonce = self._nonce(counter)
        if self._aes is not None:
            sealed = self._aes.encrypt(nonce, payload, header)
        else:
            sealed = xchacha20_poly1305_encrypt(self._key, nonce, payload, header)
        return header + sealed + counter

    def unseal(self, packet: bytes) -> tuple[RtpHeader, bytes]:
        """An incoming packet's header and payload, with any header extension's data removed.

        Raises:
            ValueError: The packet is too short to be a voice packet.
            cryptography.exceptions.InvalidTag: It was not sealed with this session's key.
        """
        header = parse_rtp(packet)
        if len(packet) < header.size + _COUNTER_SIZE:
            msg = "a voice packet is too short"
            raise ValueError(msg)
        nonce = self._nonce(packet[-_COUNTER_SIZE:])
        aad = packet[: header.size]
        sealed = packet[header.size : -_COUNTER_SIZE]
        if self._aes is not None:
            payload = self._aes.decrypt(nonce, sealed, aad)
        else:
            payload = xchacha20_poly1305_decrypt(self._key, nonce, sealed, aad)
        return header, payload[header.extension_size :]
