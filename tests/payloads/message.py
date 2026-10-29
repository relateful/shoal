import msgspec

from shoal.core.codec import decode_json, encode_json
from shoal.payloads import (
    AllowedMentions,
    AttachmentFlags,
    CreateMessageParams,
    EmbedFlags,
)


def test_unset_fields_are_omitted_and_none_is_sent_as_null() -> None:
    params = CreateMessageParams(content="hi", allowed_mentions=AllowedMentions.none())
    assert encode_json(params) == b'{"content":"hi","allowed_mentions":{"parse":[]}}'
    everyone = AllowedMentions.all()
    assert everyone.replied_user is True
    assert msgspec.json.decode(encode_json(everyone))["parse"] == ["roles", "users", "everyone"]


def test_content_scanning_flags_decode_on_attachments_and_embeds() -> None:
    # 1 << 4 | 1 << 5 | 1 << 6 | 1 << 7: explicit, animated, gore, self-harm
    attachment = decode_json(b"240", AttachmentFlags)
    assert attachment == AttachmentFlags(
        contains_explicit_content=True,
        is_animated=True,
        contains_gore_content=True,
        contains_self_harm_content=True,
    )
    assert not attachment.is_spoiler
    embed = decode_json(b"80", EmbedFlags)  # 1 << 4 | 1 << 6
    assert embed == EmbedFlags(contains_explicit_content=True, contains_gore_content=True)
    assert not embed.contains_self_harm_content
