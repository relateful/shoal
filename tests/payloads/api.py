import base64

import pytest

from shoal.payloads import image_data, sound_data

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def test_image_data_names_the_format_its_bytes_show() -> None:
    assert image_data(PNG) == f"data:image/png;base64,{base64.b64encode(PNG).decode()}"
    assert image_data(b"\xff\xd8\xff\xe0").startswith("data:image/jpeg;base64,")
    assert image_data(b"GIF89a....").startswith("data:image/gif;base64,")
    assert image_data(b"GIF87a....").startswith("data:image/gif;base64,")


def test_sound_data_names_the_format_its_bytes_show() -> None:
    assert sound_data(b"OggS\x00\x02").startswith("data:audio/ogg;base64,")
    assert sound_data(b"ID3\x04\x00").startswith("data:audio/mpeg;base64,")
    assert sound_data(b"\xff\xfb\x90\x00").startswith("data:audio/mpeg;base64,")
    with pytest.raises(ValueError, match="MP3 or Ogg"):
        sound_data(b"RIFF....WAVE")


@pytest.mark.parametrize("image", [b"", b"RIFF....WEBP", b"not an image"], ids=["empty", "webp", "text"])
def test_only_formats_discord_accepts_are_encoded(image: bytes) -> None:
    with pytest.raises(ValueError, match="PNG, JPEG or GIF"):
        image_data(image)
