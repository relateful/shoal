"""Reading a `multipart/form-data` body back, to check what an upload sent."""

from dataclasses import dataclass
from email.message import Message
from email.parser import BytesParser
from email.policy import HTTP


@dataclass(frozen=True, slots=True)
class FormPart:
    """One part of a form: its field name, filename (for files), content type and bytes."""

    name: str
    filename: str | None
    content_type: str
    data: bytes


def parse_form(body: bytes, content_type: str) -> list[FormPart]:
    """Split a form body into its parts, in order."""
    message = BytesParser(policy=HTTP).parsebytes(f"Content-Type: {content_type}\r\n\r\n".encode() + body)
    assert isinstance(message, Message)
    assert message.is_multipart()
    parts: list[FormPart] = []
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_param("filename", header="content-disposition")
        payload = part.get_payload(decode=True)
        assert isinstance(name, str)
        assert filename is None or isinstance(filename, str)
        assert isinstance(payload, bytes)
        parts.append(FormPart(name, filename, part.get_content_type(), payload))
    return parts
