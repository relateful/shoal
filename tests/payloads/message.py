import msgspec

from shoal.core.codec import encode_json
from shoal.payloads import (
    AllowedMentions,
    CreateMessageParams,
)


def test_unset_fields_are_omitted_and_none_is_sent_as_null() -> None:
    params = CreateMessageParams(content="hi", allowed_mentions=AllowedMentions.none())
    assert encode_json(params) == b'{"content":"hi","allowed_mentions":{"parse":[]}}'
    everyone = AllowedMentions.all()
    assert everyone.replied_user is True
    assert msgspec.json.decode(encode_json(everyone))["parse"] == ["roles", "users", "everyone"]
