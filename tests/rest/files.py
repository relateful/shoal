from pathlib import Path

import msgspec

from shoal.rest.files import File, encode_multipart
from tests.support.multipart import FormPart, parse_form


def test_a_form_carries_the_json_and_each_file_in_order() -> None:
    body, content_type = encode_multipart(
        b'{"content":"hi"}',
        {"files[0]": File("a.png", b"\x89PNG", content_type="image/png"), "files[1]": File("b.txt", b"text")},
    )
    assert content_type.startswith("multipart/form-data; boundary=")
    assert parse_form(body, content_type) == [
        FormPart("payload_json", None, "application/json", b'{"content":"hi"}'),
        FormPart("files[0]", "a.png", "image/png", b"\x89PNG"),
        FormPart("files[1]", "b.txt", "application/octet-stream", b"text"),
    ]


def test_a_form_without_json_has_only_the_files() -> None:
    body, content_type = encode_multipart(None, {"file": File("s.png", b"x")})
    [part] = parse_form(body, content_type)
    assert (part.name, part.filename) == ("file", "s.png")


def test_spoilers_are_marked_in_the_filename_once() -> None:
    assert File("cat.png", b"", spoiler=True).upload_name == "SPOILER_cat.png"
    assert File("SPOILER_cat.png", b"", spoiler=True).upload_name == "SPOILER_cat.png"
    assert File("cat.png", b"").upload_name == "cat.png"


def test_quotes_and_line_breaks_cannot_escape_the_header() -> None:
    body, content_type = encode_multipart(None, {"file": File('a"b\r\nX-Evil: 1.png', b"x")})
    assert b"X-Evil: 1" not in body.split(b"\r\n\r\n")[0].split(b"\r\n")[-1]
    [part] = parse_form(body, content_type)
    assert part.filename == "a%22b%0D%0AX-Evil: 1.png"


def test_the_repr_shows_the_size_not_the_contents() -> None:
    assert repr(File("a.bin", b"secret")) == "File(filename='a.bin', size=6)"


async def test_files_are_read_from_disk_off_the_loop(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_bytes(msgspec.json.encode({"ok": True}))
    file = await File.from_path(path, description="the report", spoiler=True)
    assert (file.filename, file.data, file.description, file.upload_name) == (
        "report.json",
        b'{"ok":true}',
        "the report",
        "SPOILER_report.json",
    )
