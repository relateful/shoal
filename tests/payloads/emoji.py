import base64

import pytest

from shoal.payloads import EMOJI_MAX_SIZE, emoji_content_type, emoji_data

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "
AVIF = b"\x00\x00\x00\x1cftypavif\x00\x00"


@pytest.mark.parametrize(
    ("image", "content_type"),
    [
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0", "image/jpeg"),
        (b"GIF89a....", "image/gif"),
        (WEBP, "image/webp"),
        (AVIF, "image/avif"),
        (b"\x00\x00\x00\x1cftypavis\x00\x00", "image/avif"),
    ],
)
def test_emoji_images_name_the_format_their_bytes_show(image: bytes, content_type: str) -> None:
    assert emoji_content_type(image) == content_type
    assert emoji_data(image) == f"data:{content_type};base64,{base64.b64encode(image).decode()}"


def test_other_formats_and_large_images_are_refused() -> None:
    assert emoji_content_type(b"BM bitmap") is None
    with pytest.raises(ValueError, match="JPEG, PNG, GIF, WebP or AVIF"):
        emoji_data(b"BM bitmap")
    with pytest.raises(ValueError, match="at most 256 KiB"):
        emoji_data(PNG + b"\x00" * EMOJI_MAX_SIZE)
