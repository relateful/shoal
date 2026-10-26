"""Files sent with a request, and the `multipart/form-data` body that carries them.

An endpoint that takes files sends its JSON parameters in a `payload_json` part and each file in its own
part. Message-like endpoints name the parts `files[0]`, `files[1]`…, and the matching `attachments`
entries refer to them by that index; others (stickers, soundboard sounds) use one named part.

Discord: https://docs.discord.com/developers/reference#uploading-files
"""

import asyncio
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self, override

_SPOILER_PREFIX = "SPOILER_"
"""Discord shows an attachment as a spoiler when its filename starts with this."""


@dataclass(frozen=True, slots=True)
class File:
    """A file to upload. Build one from bytes, or with `File.from_path` without blocking the loop.

    Attributes:
        filename: The name Discord shows; it is also how embeds refer to it (`attachment://name`).
        data: The file contents.
        description: Alt text for the attachment, where the endpoint supports it.
        spoiler: Hide the attachment behind a spoiler.
        content_type: The part's MIME type.
    """

    filename: str
    data: bytes
    description: str | None = None
    spoiler: bool = False
    content_type: str = "application/octet-stream"

    @classmethod
    async def from_path(
        cls,
        path: str | Path,
        *,
        filename: str | None = None,
        description: str | None = None,
        spoiler: bool = False,
    ) -> Self:
        """Read a file in a worker thread, so the event loop never waits on the disk.

        Raises:
            OSError: The file could not be read.
        """
        source = Path(path)
        data = await asyncio.to_thread(source.read_bytes)
        return cls(filename or source.name, data, description=description, spoiler=spoiler)

    @property
    def upload_name(self) -> str:
        """The filename sent to Discord, with the spoiler prefix when `spoiler` is set."""
        if self.spoiler and not self.filename.startswith(_SPOILER_PREFIX):
            return f"{_SPOILER_PREFIX}{self.filename}"
        return self.filename

    @override
    def __repr__(self) -> str:
        return f"File(filename={self.filename!r}, size={len(self.data)})"


def encode_multipart(payload_json: bytes | None, files: Mapping[str, File]) -> tuple[bytes, str]:
    """Build a `multipart/form-data` body. Returns the body and its `Content-Type` header.

    Args:
        payload_json: The JSON parameters, sent as the `payload_json` part, or `None` for none.
        files: Each part's form field name (`files[0]`, `file`…) and the file in it.
    """
    boundary = secrets.token_hex(16)
    parts: list[bytes] = []
    if payload_json is not None:
        parts.append(
            _part_head(boundary, 'form-data; name="payload_json"', "application/json")
            + payload_json
            + b"\r\n"
        )
    for field, file in files.items():
        disposition = f'form-data; name="{_quote(field)}"; filename="{_quote(file.upload_name)}"'
        parts.append(_part_head(boundary, disposition, file.content_type) + file.data + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def _part_head(boundary: str, disposition: str, content_type: str) -> bytes:
    return (
        f"--{boundary}\r\nContent-Disposition: {disposition}\r\nContent-Type: {content_type}\r\n\r\n".encode()
    )


def _quote(value: str) -> str:
    """Escape a form-data parameter value the way browsers do (RFC 7578, section 4.2)."""
    return value.replace('"', "%22").replace("\r", "%0D").replace("\n", "%0A")
