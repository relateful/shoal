"""Files sent with a request, and the `multipart/form-data` body that carries them.

An endpoint that takes files sends its JSON parameters in a `payload_json` part and each file in its own
part. Message-like endpoints name the parts `files[0]`, `files[1]`…, and the matching `attachments`
entries refer to them by that index; stickers and an invite's target user list use one named part.
(Soundboard sounds and images such as avatars are not files: they go in the JSON as data URIs.)

Discord: https://docs.discord.com/developers/reference#uploading-files
"""

import asyncio
import math
import mimetypes
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Self, override

from shoal.core.ogg import OggError, ogg_pages, opus_pre_skip
from shoal.payloads.api import ATTACHMENT_SCHEME
from shoal.payloads.message import VOICE_MESSAGE_WAVEFORM_INTERVAL, VOICE_MESSAGE_WAVEFORM_MAX_POINTS

_SPOILER_PREFIX = "SPOILER_"
"""Discord shows an attachment as a spoiler when its filename starts with this."""

_DEFAULT_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class File:
    """A file to upload. Build one from bytes, or with `File.from_path` without blocking the loop.

    Attributes:
        filename: The name Discord shows; embeds and components refer to the file by `uri`.
        data: The file contents.
        description: Alt text for the attachment. Edits can only send it when they list the
            attachments to keep (see `with_attachments`).
        spoiler: Hide the attachment behind a spoiler.
        content_type: The part's MIME type.
        duration: The length of an audio or video file in seconds; a voice message needs it.
        waveform: A voice message's waveform preview, one byte per point.

    Raises:
        ValueError: `content_type` contains a line break, which would break the request's headers.
    """

    filename: str
    data: bytes
    description: str | None = None
    spoiler: bool = False
    content_type: str = _DEFAULT_CONTENT_TYPE
    duration: float | None = None
    waveform: bytes | None = None

    def __post_init__(self) -> None:
        """Reject a content type that could inject a header into the multipart body."""
        if "\r" in self.content_type or "\n" in self.content_type:
            msg = "a file's content type cannot contain a line break"
            raise ValueError(msg)

    @classmethod
    async def from_path(
        cls,
        path: str | Path,
        *,
        filename: str | None = None,
        description: str | None = None,
        spoiler: bool = False,
        content_type: str | None = None,
    ) -> Self:
        """Read a file in a worker thread, so the event loop never waits on the disk.

        Without `content_type`, it is guessed from the filename's extension.

        Raises:
            OSError: The file could not be read.
        """
        source = Path(path)
        data = await asyncio.to_thread(source.read_bytes)
        name = filename or source.name
        guessed, _ = mimetypes.guess_type(name)
        return cls(
            name,
            data,
            description=description,
            spoiler=spoiler,
            content_type=content_type or guessed or _DEFAULT_CONTENT_TYPE,
        )

    @property
    def upload_name(self) -> str:
        """The filename sent to Discord, with the spoiler prefix when `spoiler` is set."""
        if self.spoiler and not self.filename.startswith(_SPOILER_PREFIX):
            return f"{_SPOILER_PREFIX}{self.filename}"
        return self.filename

    @property
    def uri(self) -> str:
        """How an embed or a component refers to the file sent with the same message."""
        return f"{ATTACHMENT_SCHEME}{self.upload_name}"

    @override
    def __repr__(self) -> str:
        return f"File(filename={self.filename!r}, size={len(self.data)})"


_FLAT_LEVEL: Final = 128
"""The waveform point used when a voice message's waveform is not known: a steady middle level."""

_OPUS_RATE: Final = 48_000
"""Opus counts its granule positions in samples at 48 kHz, whatever rate the audio was recorded at."""


@dataclass(frozen=True, slots=True)
class VoiceMessage:
    """A voice message to send: a single audio file Discord plays inline, with a waveform preview.

    Send one with `channel.send(voice_message=...)`; it can have no content, embeds, other files or
    components, and cannot be edited later. Discord's own clients record one channel of 48 kHz Opus
    in an Ogg container.

    Attributes:
        data: The audio.
        duration: Its length in seconds.
        waveform: Up to `VOICE_MESSAGE_WAVEFORM_MAX_POINTS` points, one byte each, spread over the
            recording (Discord's clients take one every `VOICE_MESSAGE_WAVEFORM_INTERVAL` seconds).
        filename: The attachment's name.
        content_type: The audio's MIME type; it must start with `audio/`.

    Raises:
        ValueError: A duration that is not positive, an empty or too long waveform, or a content
            type that is not audio.

    Discord: https://docs.discord.com/developers/resources/message#voice-messages
    """

    data: bytes
    duration: float
    waveform: bytes
    filename: str = "voice-message.ogg"
    content_type: str = "audio/ogg"

    def __post_init__(self) -> None:
        """Check what Discord requires of a voice message's metadata."""
        if not self.duration > 0:
            msg = "a voice message needs a positive duration"
            raise ValueError(msg)
        if not 0 < len(self.waveform) <= VOICE_MESSAGE_WAVEFORM_MAX_POINTS:
            msg = f"a voice message's waveform has 1 to {VOICE_MESSAGE_WAVEFORM_MAX_POINTS} points"
            raise ValueError(msg)
        if not self.content_type.startswith("audio/"):
            msg = "a voice message's content type must start with audio/"
            raise ValueError(msg)

    @classmethod
    def from_ogg(
        cls, data: bytes, *, waveform: bytes | None = None, filename: str = "voice-message.ogg"
    ) -> Self:
        """A voice message from Ogg Opus audio, its duration read from the stream.

        Without `waveform`, the preview is flat: computing one needs the decoded audio (see
        `waveform_of`).

        Raises:
            ValueError: `data` is not an Ogg Opus stream.
        """
        duration = ogg_opus_duration(data)
        return cls(data, duration, waveform if waveform is not None else flat_waveform(duration), filename)

    @classmethod
    async def from_path(cls, path: str | Path, *, waveform: bytes | None = None) -> Self:
        """`from_ogg` on a file, read in a worker thread so the event loop never waits on the disk.

        Raises:
            OSError: The file could not be read.
            ValueError: It is not an Ogg Opus stream.
        """
        source = Path(path)
        return cls.from_ogg(
            await asyncio.to_thread(source.read_bytes), waveform=waveform, filename=source.name
        )

    @property
    def file(self) -> File:
        """The attachment that carries it."""
        return File(
            self.filename,
            self.data,
            content_type=self.content_type,
            duration=self.duration,
            waveform=self.waveform,
        )

    @override
    def __repr__(self) -> str:
        return f"VoiceMessage(duration={self.duration:.2f}, size={len(self.data)})"


def ogg_opus_duration(data: bytes) -> float:
    """The length in seconds of an Ogg Opus stream, read from its headers without decoding it.

    The last page's granule position counts every sample at 48 kHz, including the encoder's
    pre-skip, which the `OpusHead` header gives.

    Raises:
        ValueError: `data` is not an Ogg Opus stream.

    Opus in Ogg: https://www.rfc-editor.org/rfc/rfc7845#section-4
    """
    pages = list(ogg_pages(data))
    if not pages:
        msg = "not an Ogg Opus stream"
        raise OggError(msg)
    pre_skip = opus_pre_skip(pages[0].body)
    granule = pages[-1].granule
    if granule <= pre_skip:
        msg = "the Ogg Opus stream holds no audio"
        raise ValueError(msg)
    return (granule - pre_skip) / _OPUS_RATE


def flat_waveform(duration: float) -> bytes:
    """A steady waveform for a recording of `duration` seconds, one point per interval Discord samples."""
    points = math.ceil(duration / VOICE_MESSAGE_WAVEFORM_INTERVAL)
    return bytes([_FLAT_LEVEL]) * max(1, min(points, VOICE_MESSAGE_WAVEFORM_MAX_POINTS))


def waveform_of(levels: Sequence[float]) -> bytes:
    """A waveform preview from loudness levels between 0 and 1, spread evenly over the recording.

    Give one level per `VOICE_MESSAGE_WAVEFORM_INTERVAL` (the peak of each slice, for example); a
    longer recording is downsampled to `VOICE_MESSAGE_WAVEFORM_MAX_POINTS` points, each the loudest of
    the levels it covers.

    Raises:
        ValueError: `levels` is empty.
    """
    if not levels:
        msg = "a waveform needs at least one level"
        raise ValueError(msg)
    points = min(len(levels), VOICE_MESSAGE_WAVEFORM_MAX_POINTS)
    out = bytearray()
    for point in range(points):
        start = point * len(levels) // points
        end = max(start + 1, (point + 1) * len(levels) // points)
        loudest = max(levels[start:end])
        # Out of range is clamped; NaN (no level known) reads as silence.
        out.append(0 if math.isnan(loudest) else round(min(max(loudest, 0.0), 1.0) * 255))
    return bytes(out)


def encode_multipart(
    payload_json: bytes | None, files: Mapping[str, File], fields: Mapping[str, str] | None = None
) -> tuple[bytes, str]:
    """Build a `multipart/form-data` body. Returns the body and its `Content-Type` header.

    Each file's bytes are copied once, into the body.

    Args:
        payload_json: The JSON parameters, sent as the `payload_json` part, or `None` for none.
        files: Each part's form field name (`files[0]`, `file`…) and the file in it.
        fields: Plain text form fields, for endpoints that take their parameters that way.
    """
    boundary = secrets.token_hex(16)
    pieces: list[bytes] = []
    for name, value in (fields or {}).items():
        pieces += [f'--{boundary}\r\nContent-Disposition: form-data; name="{_quote(name)}"\r\n\r\n'.encode()]
        pieces += [value.encode(), b"\r\n"]
    if payload_json is not None:
        pieces += [
            _part_head(boundary, 'form-data; name="payload_json"', "application/json"),
            payload_json,
            b"\r\n",
        ]
    for field, file in files.items():
        disposition = f'form-data; name="{_quote(field)}"; filename="{_quote(file.upload_name)}"'
        pieces += [_part_head(boundary, disposition, file.content_type), file.data, b"\r\n"]
    pieces.append(f"--{boundary}--\r\n".encode())
    return b"".join(pieces), f"multipart/form-data; boundary={boundary}"


def _part_head(boundary: str, disposition: str, content_type: str) -> bytes:
    return (
        f"--{boundary}\r\nContent-Disposition: {disposition}\r\nContent-Type: {content_type}\r\n\r\n".encode()
    )


def _quote(value: str) -> str:
    """Escape a form-data parameter value the way browsers do (RFC 7578, section 4.2)."""
    return value.replace('"', "%22").replace("\r", "%0D").replace("\n", "%0A")
