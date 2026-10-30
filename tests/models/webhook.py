import msgspec
import pytest

from shoal.core.codec import decode_json, encode_json
from shoal.core.snowflake import Snowflake
from shoal.models.base import Object
from shoal.models.colour import Colour
from shoal.models.embed import Embed
from shoal.models.webhook import Webhook, WebhookMessage
from shoal.payloads.webhook import Webhook as WebhookPayload
from shoal.payloads.webhook import WebhookType
from tests.support.fakes import FakeTransport
from tests.support.models import message
from tests.support.rest import API, make_client

HOOK = 112233445566778899
TOKEN = "tok-en_1.2"
URL = f"https://discord.com/api/webhooks/{HOOK}/{TOKEN}"


def webhook_json(**extra: object) -> dict[str, object]:
    return {
        "id": str(HOOK),
        "type": 1,
        "channel_id": "5",
        "name": "CI",
        "avatar": None,
        "application_id": None,
    } | extra


def last(transport: FakeTransport) -> tuple[str, str, object]:
    sent = transport.requests[-1]
    body = None if not sent.body else msgspec.json.decode(sent.body)
    return sent.method, sent.url.removeprefix(API), body


def hook(transport: FakeTransport) -> Webhook:
    return Webhook.from_url(URL, rest=make_client(transport))


@pytest.mark.parametrize(
    "url",
    [
        URL,
        f"https://canary.discord.com/api/v10/webhooks/{HOOK}/{TOKEN}/",
        f"https://discordapp.com/api/webhooks/{HOOK}/{TOKEN}",
    ],
)
def test_from_url_reads_id_and_token(url: str) -> None:
    webhook = Webhook.from_url(url, rest=make_client(FakeTransport()))
    assert webhook.id == HOOK
    assert webhook.token == TOKEN
    assert webhook.url == URL
    assert webhook.type is WebhookType.INCOMING
    assert webhook.name is None
    assert webhook.channel_id is None
    assert webhook.guild_id is None


def test_from_url_refuses_other_urls_and_repr_hides_the_token() -> None:
    with pytest.raises(ValueError, match="not a webhook URL"):
        Webhook.from_url("https://example.com/webhooks/1/x", rest=make_client(FakeTransport()))
    assert TOKEN not in repr(hook(FakeTransport()))


async def test_send_without_wait_returns_nothing() -> None:
    transport = FakeTransport()
    transport.queue(204)
    sent = await hook(transport).send("hi", username="Bot", avatar_url="https://a/b.png", silent=True)
    assert sent is None
    assert last(transport) == (
        "POST",
        f"/webhooks/{HOOK}/{TOKEN}",
        {"content": "hi", "username": "Bot", "avatar_url": "https://a/b.png", "flags": 1 << 12},
    )


async def test_send_with_wait_in_a_forum_returns_the_message() -> None:
    transport = FakeTransport()
    transport.queue(200, message(9, channel_id=77))
    sent = await hook(transport).send(
        embed=Embed(title="t", colour=Colour.red()),
        thread_name="post",
        applied_tags=[Object(3)],
        wait=True,
    )
    assert isinstance(sent, WebhookMessage)
    assert sent.id == 9
    assert sent.channel_id == 77
    assert sent.content == "hello"
    assert sent.attachments == []
    assert sent.embeds == []
    assert sent.payload.id == 9
    assert repr(sent) == f"<WebhookMessage id=9 webhook={HOOK}>"
    assert last(transport) == (
        "POST",
        f"/webhooks/{HOOK}/{TOKEN}?wait=true",
        {"embeds": [{"title": "t", "color": 0xE74C3C}], "thread_name": "post", "applied_tags": ["3"]},
    )


async def test_messages_in_a_thread_are_fetched_edited_and_deleted_there() -> None:
    transport = FakeTransport()
    webhook = hook(transport)
    transport.queue(200, message(9))
    fetched = await webhook.fetch_message(9, thread=Object(44))
    assert last(transport)[:2] == ("GET", f"/webhooks/{HOOK}/{TOKEN}/messages/9?thread_id=44")
    transport.queue(200, message(9, content="new"))
    edited = await fetched.edit(content="new")
    assert edited.content == "new"
    assert last(transport) == (
        "PATCH",
        f"/webhooks/{HOOK}/{TOKEN}/messages/9?thread_id=44",
        {"content": "new"},
    )
    transport.queue(204)
    await edited.delete()
    assert last(transport)[:2] == ("DELETE", f"/webhooks/{HOOK}/{TOKEN}/messages/9?thread_id=44")


async def test_fetch_edit_and_delete_use_the_token_and_keep_it() -> None:
    transport = FakeTransport()
    webhook = hook(transport)
    transport.queue(200, webhook_json())
    fetched = await webhook.fetch()
    assert last(transport)[:2] == ("GET", f"/webhooks/{HOOK}/{TOKEN}")
    assert fetched.name == "CI"
    assert fetched.channel_id == Snowflake(5)
    assert fetched.token == TOKEN
    assert fetched.payload.name == "CI"
    transport.queue(200, webhook_json(name="Deploys"))
    renamed = await fetched.edit(name="Deploys", avatar=None)
    assert last(transport) == ("PATCH", f"/webhooks/{HOOK}/{TOKEN}", {"name": "Deploys", "avatar": None})
    assert renamed.token == TOKEN
    transport.queue(204)
    await renamed.delete()
    assert last(transport)[:2] == ("DELETE", f"/webhooks/{HOOK}/{TOKEN}")


async def test_without_a_token_it_uses_the_bot_token_and_cannot_send() -> None:
    transport = FakeTransport()
    data = decode_json(encode_json(webhook_json(type=2)), WebhookPayload)
    webhook = Webhook(data, rest=make_client(transport))
    assert webhook.token is None
    assert webhook.url is None
    transport.queue(200, webhook_json(type=2))
    await webhook.fetch()
    assert last(transport)[:2] == ("GET", f"/webhooks/{HOOK}")
    transport.queue(200, webhook_json(type=2, channel_id="6"))
    await webhook.edit(channel=Object(6), reason="move")
    assert last(transport) == ("PATCH", f"/webhooks/{HOOK}", {"channel_id": "6"})
    transport.queue(204)
    await webhook.delete(reason="gone")
    assert last(transport)[:2] == ("DELETE", f"/webhooks/{HOOK}")
    with pytest.raises(ValueError, match="no token"):
        await webhook.send("hi")
