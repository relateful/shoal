"""Files sent with a request, and the `multipart/form-data` body that carries them.

An endpoint that takes files sends its JSON parameters in a `payload_json` part and each file in its own
part. Message-like endpoints name the parts `files[0]`, `files[1]`…, and the matching `attachments`
entries refer to them by that index; stickers and an invite's target user list use one named part.
(Soundboard sounds and images such as avatars are not files: they go in the JSON as data URIs.)

Discord: https://docs.discord.com/developers/reference#uploading-files
"""

import asyncio
import mimetypes
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self, override

_SPOILER_PREFIX = "SPOILER_"
"""Discord shows an attachment as a spoiler when its filename starts with this."""

_DEFAULT_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class File:
    """A file to upload. Build one from bytes, or with `File.from_path` without blocking the loop.

    Attributes:
        filename: The name Discord shows; it is also how embeds refer to it (`attachment://name`).
        data: The file contents.
        description: Alt text for the attachment. Edits can only send it when they list the
            attachments to keep (see `with_attachments`).
        spoiler: Hide the attachment behind a spoiler.
        content_type: The part's MIME type.

    Raises:
        ValueError: `content_type` contains a line break, which would break the request's headers.
    """

    filename: str
    data: bytes
    description: str | None = None
    spoiler: bool = False
    content_type: str = _DEFAULT_CONTENT_TYPE

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

    @override
    def __repr__(self) -> str:
        return f"File(filename={self.filename!r}, size={len(self.data)})"


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
