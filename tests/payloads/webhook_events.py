"""Webhook event payloads, decoded from the examples in Discord's docs (user objects filled in)."""

from datetime import datetime

from msgspec import UNSET, UnsetType

from shoal.core.codec import decode_json, encode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    WEBHOOK_EVENT_PAYLOADS,
    ApplicationAuthorized,
    ApplicationDeauthorized,
    ApplicationIntegrationType,
    GameDirectMessage,
    LobbyMessageDelete,
    WebhookEventPayload,
    WebhookEventType,
    WebhookLobbyMessage,
    WebhookPayloadType,
)
from tests.support.models import user

type Json = dict[str, object]


def request(event_type: str, data: Json | None) -> WebhookEventPayload:
    body: Json = {"type": event_type, "timestamp": "2024-10-18T14:42:53.064834"}
    if data is not None:
        body["data"] = data
    raw: Json = {"version": 1, "application_id": "1234560123453231555", "type": 1, "event": body}
    return decode_json(encode_json(raw), WebhookEventPayload)


def data_of[T](payload: WebhookEventPayload, kind: type[T]) -> T:
    assert not isinstance(payload.event, UnsetType)
    assert not isinstance(payload.event.data, UnsetType)
    assert WEBHOOK_EVENT_PAYLOADS[payload.event.type] is kind
    return decode_json(payload.event.data, kind)


def test_a_ping_has_no_event() -> None:
    ping = decode_json(b'{"version": 1, "application_id": "5", "type": 0}', WebhookEventPayload)
    assert ping.type is WebhookPayloadType.PING
    assert ping.event is UNSET
    assert ping.application_id == Snowflake(5)


def test_application_authorized_and_deauthorized() -> None:
    authorized = request(
        "APPLICATION_AUTHORIZED",
        {"integration_type": 1, "scopes": ["applications.commands"], "user": user(9, "ada")},
    )
    assert not isinstance(authorized.event, UnsetType)
    assert authorized.event.timestamp == datetime(2024, 10, 18, 14, 42, 53, 64834)  # noqa: DTZ001
    found = data_of(authorized, ApplicationAuthorized)
    assert found.integration_type is ApplicationIntegrationType.USER_INSTALL
    assert found.scopes == ["applications.commands"]
    assert found.guild is UNSET
    gone = data_of(request("APPLICATION_DEAUTHORIZED", {"user": user(9, "ada")}), ApplicationDeauthorized)
    assert gone.user.id == 9


def test_lobby_messages() -> None:
    message = data_of(
        request(
            "LOBBY_MESSAGE_CREATE",
            {
                "id": "1397729799727878254",
                "type": 0,
                "content": "welcome to the lobby!",
                "lobby_id": "1397729744753266719",
                "channel_id": "1397729744753266719",
                "author": user(9, "ada"),
                "metadata": {},
                "flags": 0,
                "application_id": "1234567765431056709",
            },
        ),
        WebhookLobbyMessage,
    )
    assert message.content == "welcome to the lobby!"
    deleted = data_of(
        request("LOBBY_MESSAGE_DELETE", {"id": "1402406637632884857", "lobby_id": "1402399883394285659"}),
        LobbyMessageDelete,
    )
    assert deleted.lobby_id == 1402399883394285659


def test_game_direct_messages_in_both_shapes() -> None:
    channel: Json = {"id": "1405604229820715098", "type": 1, "recipients": [user(9, "ada")]}
    standard = data_of(
        request(
            "GAME_DIRECT_MESSAGE_DELETE",
            {
                "id": "1407771600643686503",
                "type": 0,
                "content": "cant make it in time",
                "channel_id": "1405604229820715098",
                "channel": channel,
                "author": user(9, "ada"),
                "timestamp": "2025-08-20T17:01:44.725000+00:00",
                "flags": 0,
                "attachments": [],
                "components": [],
            },
        ),
        GameDirectMessage,
    )
    assert not standard.is_sdk_message()
    in_game = data_of(
        request(
            "GAME_DIRECT_MESSAGE_CREATE",
            {
                "id": "1",
                "type": 0,
                "content": "gg",
                "author": user(9, "ada"),
                "flags": 0,
                "application_id": "2",
                "channel": channel,
            },
        ),
        GameDirectMessage,
    )
    assert in_game.is_sdk_message()


def test_every_event_type_has_an_entry() -> None:
    assert set(WEBHOOK_EVENT_PAYLOADS) == set(WebhookEventType)
    assert WEBHOOK_EVENT_PAYLOADS[WebhookEventType.QUEST_USER_ENROLLMENT] is None


def test_an_event_type_newer_than_shoal_still_decodes() -> None:
    newer = request("SOMETHING_NEW", None)
    assert not isinstance(newer.event, UnsetType)
    assert newer.event.type == "SOMETHING_NEW"
    assert newer.event.type not in WEBHOOK_EVENT_PAYLOADS
