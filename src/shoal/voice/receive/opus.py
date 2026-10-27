"""A small typed binding to libopus's decoder, through `ctypes`.

libopus is a system library, not a Python package: install it with the system's package manager
(`apt install libopus0`, `brew install opus`); on Windows, put `opus.dll` in a folder on `PATH` or
give `load_opus` its full path (Windows does not search the bot's folder). Shoal finds it on first
use; `load_opus` names it explicitly.

Only decoding is bound: Shoal sends Opus as it comes (`OggOpusSource`, `FFmpegSource`), so receiving
is the one place PCM is needed.

libopus: https://opus-codec.org/docs/opus_api-1.5/group__opus__decoder.html
"""

import ctypes
import ctypes.util
import sys
from typing import Final, Protocol, cast, final

from shoal.core.errors import ShoalError
from shoal.voice.defaults import FIRST_LOSS_SAMPLES
from shoal.voice.rtp import opus_samples

CHANNELS: Final = 2
"""Decoded PCM is stereo, interleaved."""

SAMPLE_RATE: Final = 48000
"""Discord's Opus sample rate, and the rate decoded PCM comes out at."""

SAMPLE_WIDTH: Final = 2
"""Bytes per sample: signed 16-bit, little-endian (the machine's order on every platform Shoal runs on)."""

_MAX_FRAME: Final = 5760
"""The most samples per channel one Opus packet can hold (120 ms at 48 kHz)."""

_OK: Final = 0

_NAMES: Final = ("opus", "libopus-0", "libopus")
"""Names `ctypes.util.find_library` is asked for, in order."""


class OpusError(ShoalError):
    """libopus could not be loaded, or refused a call.

    Attributes:
        code: libopus's error code, when it gave one.
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        """Create the error."""
        super().__init__(message)
        self.code: int | None = code


class OpusLibrary(Protocol):
    """The libopus functions the decoder calls; tests pass a fake."""

    __slots__ = ()

    def opus_decoder_create(self, sample_rate: int, channels: int, error: ctypes.c_int, /) -> int | None:
        """A new decoder state, or `None` with `error` set."""
        ...

    def opus_decode(  # noqa: PLR0917 - libopus's signature
        self,
        state: int,
        data: bytes | None,
        length: int,
        pcm: "ctypes.Array[ctypes.c_int16]",
        frame_size: int,
        decode_fec: int,
        /,
    ) -> int:
        """Decode one packet into `pcm`; samples per channel, or a negative error code."""
        ...

    def opus_decoder_destroy(self, state: int, /) -> None:
        """Free a decoder state."""
        ...

    def opus_strerror(self, code: int, /) -> bytes:
        """The description libopus gives an error code."""
        ...


_library: OpusLibrary | None = None


def _bind(path: str) -> OpusLibrary:
    library = ctypes.CDLL(path)
    library.opus_decoder_create.argtypes = (ctypes.c_int32, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
    library.opus_decoder_create.restype = ctypes.c_void_p
    library.opus_decode.argtypes = (
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int16),
        ctypes.c_int,
        ctypes.c_int,
    )
    library.opus_decode.restype = ctypes.c_int
    library.opus_decoder_destroy.argtypes = (ctypes.c_void_p,)
    library.opus_decoder_destroy.restype = None
    library.opus_strerror.argtypes = (ctypes.c_int,)
    library.opus_strerror.restype = ctypes.c_char_p
    return cast("OpusLibrary", library)  # a CDLL's functions are untyped


def load_opus(path: str) -> None:
    """Load libopus from `path` (a file name or a full path) instead of searching for it.

    Raises:
        OpusError: The library could not be loaded or lacks the decoder functions.
    """
    global _library  # noqa: PLW0603 - one library per process, as in libopus itself
    try:
        _library = _bind(path)
    except (OSError, AttributeError) as error:
        msg = f"libopus could not be loaded from {path!r}: {error}"
        raise OpusError(msg) from error


def is_loaded() -> bool:
    """Whether libopus is loaded (by `load_opus`, or by a decoder's first use)."""
    return _library is not None


def _find() -> OpusLibrary:
    if _library is not None:
        return _library
    candidates = [found for name in _NAMES if (found := ctypes.util.find_library(name)) is not None]
    if sys.platform == "win32":
        candidates += ["opus.dll", "libopus-0.dll"]
    for candidate in candidates:
        try:
            load_opus(candidate)
        except OpusError:
            continue
        return cast("OpusLibrary", _library)  # load_opus set it; the checker cannot see through the global
    msg = (
        "libopus was not found: install it (apt install libopus0, brew install opus, or opus.dll on PATH on "
        "Windows) or name it with shoal.voice.receive.load_opus(path)"
    )
    raise OpusError(msg)


@final
class OpusDecoder:
    """Decodes one sender's Opus packets to 48 kHz stereo PCM (signed 16-bit, interleaved).

    A decoder keeps state between packets, so each audio stream needs its own.

    Args:
        library: libopus; found on first use when left out.

    Raises:
        OpusError: libopus is missing or could not create a decoder.
    """

    __slots__ = ("_last_samples", "_library", "_pcm", "_state")

    def __init__(self, *, library: OpusLibrary | None = None) -> None:
        """Create a decoder; see the class docstring for the arguments."""
        self._state: int | None = None  # set first: `__del__` runs even when creating fails
        self._library: OpusLibrary = library or _find()
        error = ctypes.c_int(_OK)
        state = self._library.opus_decoder_create(SAMPLE_RATE, CHANNELS, error)
        if not state or error.value != _OK:
            doing = "create a decoder"
            raise self._error(doing, error.value)
        self._state = state
        self._pcm: ctypes.Array[ctypes.c_int16] = (ctypes.c_int16 * (_MAX_FRAME * CHANNELS))()
        self._last_samples: int = FIRST_LOSS_SAMPLES

    def decode(self, packet: bytes) -> bytes:
        """One packet's audio.

        Raises:
            OpusError: The packet is corrupt, or the decoder is closed.
            ValueError: The packet has no TOC byte.
        """
        samples = opus_samples(packet)
        decoded = self._run(packet, min(samples, _MAX_FRAME), fec=False)
        self._last_samples = decoded // CHANNELS // SAMPLE_WIDTH or self._last_samples
        return self._pcm_bytes(decoded)

    def conceal(self, next_packet: bytes | None = None) -> bytes:
        """Audio standing in for one lost packet, as long as the last one decoded.

        With the packet after the loss, its forward error correction data rebuilds the lost audio
        when the sender included it; otherwise libopus conceals the gap from what came before.

        Raises:
            OpusError: The decoder is closed or refused the call.
        """
        decoded = self._run(next_packet, self._last_samples, fec=next_packet is not None)
        return self._pcm_bytes(decoded)

    def close(self) -> None:
        """Free the decoder; it cannot be used after. Closing twice does nothing."""
        if self._state is not None:
            self._library.opus_decoder_destroy(self._state)
            self._state = None

    def __del__(self) -> None:
        """Free the decoder if it was not closed."""
        self.close()

    def _run(self, packet: bytes | None, frame_size: int, *, fec: bool) -> int:
        if self._state is None:
            msg = "the Opus decoder is closed"
            raise OpusError(msg)
        length = 0 if packet is None else len(packet)
        samples = self._library.opus_decode(self._state, packet, length, self._pcm, frame_size, int(fec))
        if samples < 0:
            doing = "decode a packet"
            raise self._error(doing, samples)
        return samples * CHANNELS * SAMPLE_WIDTH

    def _pcm_bytes(self, size: int) -> bytes:
        return ctypes.string_at(self._pcm, size)

    def _error(self, doing: str, code: int) -> OpusError:
        reason = self._library.opus_strerror(code).decode(errors="replace")
        return OpusError(f"libopus could not {doing}: {reason}", code=code)
