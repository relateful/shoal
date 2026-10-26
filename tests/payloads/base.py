import msgspec
import pytest

from shoal.core.codec import decode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    AddMemberParams,
    CreateGroupDMParams,
    CreateOrJoinLobbyParams,
    Webhook,
    WebhookType,
)
from shoal.payloads.base import Payload
from tests.support.calls import call_unchecked


class Sample(Payload):
    optional: int | None = None
    required: str


def test_payloads_are_keyword_only_so_fields_keep_discord_order() -> None:
    assert Sample(required="x").optional is None
    with pytest.raises(TypeError):
        call_unchecked(Sample, "x")


def test_unknown_fields_from_discord_are_ignored() -> None:
    assert decode_json(b'{"required":"x","added_by_discord_later":1}', Sample) == Sample(required="x")


def test_payloads_skip_the_cycle_collector_by_default() -> None:
    assert Sample.__struct_config__.gc is False
    assert msgspec.Struct.__struct_config__.gc is True


def test_options_can_still_be_overridden() -> None:
    class Frozen(Payload, frozen=True):
        value: int

    field = "value"
    with pytest.raises(AttributeError):
        setattr(Frozen(value=1), field, 2)


def test_credentials_never_appear_in_a_repr() -> None:
    member = AddMemberParams(access_token="OAUTH-SECRET", nick="Ada")
    assert "OAUTH-SECRET" not in repr(member)
    assert "access_token=<redacted>" in repr(member)
    assert "nick='Ada'" in repr(member)
    hook = Webhook(
        id=Snowflake(1),
        type=WebhookType.INCOMING,
        channel_id=None,
        name=None,
        avatar=None,
        token="HOOK-SECRET",
        application_id=None,
        url="https://discord.com/api/webhooks/1/HOOK-SECRET",
    )
    assert "HOOK-SECRET" not in repr(hook)
    lobby = CreateOrJoinLobbyParams(secret="LOBBY-SECRET")
    assert "LOBBY-SECRET" not in repr(lobby)
    assert "TOKENS" not in repr(CreateGroupDMParams(access_tokens=["TOKENS"], nicks={}))


def test_payloads_without_credentials_show_every_field() -> None:
    assert repr(Sample(required="x")) == "Sample(optional=None, required='x')"
