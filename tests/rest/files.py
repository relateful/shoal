from pathlib import Path

import msgspec
import pytest

from shoal.payloads.message import VOICE_MESSAGE_WAVEFORM_MAX_POINTS
from shoal.rest.files import (
    File,
    VoiceMessage,
    encode_multipart,
    flat_waveform,
    ogg_opus_duration,
    waveform_of,
)
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


def test_text_fields_come_before_the_files() -> None:
    body, content_type = encode_multipart(
        None, {"file": File("s.png", b"x")}, {"name": "party", "tags": "tada"}
    )
    assert [(part.name, part.filename, part.data) for part in parse_form(body, content_type)] == [
        ("name", None, b"party"),
        ("tags", None, b"tada"),
        ("file", "s.png", b"x"),
    ]


def test_a_content_type_cannot_inject_a_header() -> None:
    with pytest.raises(ValueError, match="line break"):
        File("a.png", b"x", content_type="image/png\r\nX-Evil: 1")


async def test_the_content_type_is_guessed_from_the_extension(tmp_path: Path) -> None:
    (tmp_path / "chart.png").write_bytes(b"\x89PNG")
    (tmp_path / "data.unknownext").write_bytes(b"?")
    assert (await File.from_path(tmp_path / "chart.png")).content_type == "image/png"
    assert (await File.from_path(tmp_path / "data.unknownext")).content_type == "application/octet-stream"
    given = await File.from_path(tmp_path / "chart.png", content_type="image/apng")
    assert given.content_type == "image/apng"


def ogg_opus(seconds: float, pre_skip: int = 312, *, audio: bytes = b"audio", pages: int = 1) -> bytes:
    """A minimal Ogg Opus stream: the OpusHead page, then audio pages whose last granule ends it."""

    def page(granule: int, packet: bytes) -> bytes:
        header = b"OggS" + bytes([0, 0]) + granule.to_bytes(8, "little") + bytes(12) + bytes([1, len(packet)])
        return header + packet

    head = (
        b"OpusHead"
        + bytes([1, 1])
        + pre_skip.to_bytes(2, "little")
        + (48_000).to_bytes(4, "little")
        + bytes(3)
    )
    end = pre_skip + round(seconds * 48_000)
    middle = b"".join(page(end * index // pages, audio) for index in range(1, pages))
    return page(0, head) + middle + page(end, audio)


def test_a_voice_message_reads_its_duration_from_the_ogg_stream() -> None:
    voice = VoiceMessage.from_ogg(ogg_opus(3.0))
    assert voice.duration == 3.0
    assert voice.waveform == bytes([128]) * 30  # one point per 100 ms, flat without the audio
    assert repr(voice) == f"VoiceMessage(duration=3.00, size={len(voice.data)})"
    attached = voice.file
    assert (attached.filename, attached.content_type, attached.duration, attached.waveform) == (
        "voice-message.ogg",
        "audio/ogg",
        3.0,
        voice.waveform,
    )
    assert len(VoiceMessage.from_ogg(ogg_opus(60.0)).waveform) == VOICE_MESSAGE_WAVEFORM_MAX_POINTS
    given = VoiceMessage.from_ogg(ogg_opus(1.0), waveform=b"\x01\x02")
    assert given.waveform == b"\x01\x02"


def test_the_duration_comes_from_the_last_page_whatever_the_audio_holds() -> None:
    # Audio bytes that spell the page marker must not be read as a page.
    assert ogg_opus_duration(ogg_opus(2.0, audio=b"xxOggS" + bytes(20))) == 2.0
    assert ogg_opus_duration(ogg_opus(4.0, pages=5)) == 4.0
    with pytest.raises(ValueError, match="cut short"):
        ogg_opus_duration(ogg_opus(1.0)[:-2])
    with pytest.raises(ValueError, match="not an Ogg Opus stream"):
        ogg_opus_duration(b"")


def test_only_ogg_opus_audio_is_read() -> None:
    with pytest.raises(ValueError, match="not an Ogg stream"):
        ogg_opus_duration(b"RIFF....WAVE")
    with pytest.raises(ValueError, match="not an Ogg"):
        ogg_opus_duration(b"OggS" + bytes(30))
    with pytest.raises(ValueError, match="holds no audio"):
        ogg_opus_duration(ogg_opus(0.0))


def test_a_voice_message_has_what_discord_requires() -> None:
    with pytest.raises(ValueError, match="positive duration"):
        VoiceMessage(b"x", 0.0, b"\x01")
    with pytest.raises(ValueError, match="1 to 256 points"):
        VoiceMessage(b"x", 1.0, b"")
    with pytest.raises(ValueError, match="1 to 256 points"):
        VoiceMessage(b"x", 1.0, bytes(257))
    with pytest.raises(ValueError, match="audio/"):
        VoiceMessage(b"x", 1.0, b"\x01", content_type="video/mp4")


async def test_a_voice_message_is_read_from_disk_off_the_loop(tmp_path: Path) -> None:
    path = tmp_path / "hello.ogg"
    path.write_bytes(ogg_opus(2.5))
    voice = await VoiceMessage.from_path(path)
    assert (voice.filename, voice.duration) == ("hello.ogg", 2.5)


def test_a_waveform_keeps_the_loudest_level_of_each_point() -> None:
    assert waveform_of([0.0, 0.5, 1.0, 2.0, -1.0]) == bytes([0, 128, 255, 255, 0])
    long = waveform_of([0.1] * 511 + [1.0])
    assert len(long) == VOICE_MESSAGE_WAVEFORM_MAX_POINTS
    assert long[-1] == 255
    assert set(long[:-1]) == {26}
    assert waveform_of([float("nan"), 0.5]) == bytes([0, 128])  # an unknown level reads as silence
    with pytest.raises(ValueError, match="at least one level"):
        waveform_of([])
    assert flat_waveform(0.01) == bytes([128])
