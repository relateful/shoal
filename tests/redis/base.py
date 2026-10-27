from shoal.redis.base import key_of, text_of


def test_keys_join_their_parts_under_the_prefix() -> None:
    assert key_of("bot", "sessions", 3) == "bot:sessions:3"
    assert key_of("bot") == "bot"


def test_values_read_back_as_bytes_whatever_the_client_decodes() -> None:
    assert text_of("é") == "é".encode()
    assert text_of(b"x") == b"x"
