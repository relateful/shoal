import base64

import pytest

from shoal.payloads import image_data

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def test_image_data_names_the_format_its_bytes_show() -> None:
    assert image_data(PNG) == f"data:image/png;base64,{base64.b64encode(PNG).decode()}"
    assert image_data(b"\xff\xd8\xff\xe0").startswith("data:image/jpeg;base64,")
    assert image_data(b"GIF89a....").startswith("data:image/gif;base64,")
    assert image_data(b"GIF87a....").startswith("data:image/gif;base64,")


@pytest.mark.parametrize("image", [b"", b"RIFF....WEBP", b"not an image"], ids=["empty", "webp", "text"])
def test_only_formats_discord_accepts_are_encoded(image: bytes) -> None:
    with pytest.raises(ValueError, match="PNG, JPEG or GIF"):
        image_data(image)
