import asyncio
from collections.abc import Sequence
from datetime import timedelta

import msgspec
import pytest

from shoal.client.client import Client
from shoal.client.interaction import Interaction, InteractionRespondedError
from shoal.models.channel import TextChannel
from shoal.models.embed import Embed
from shoal.models.member import Member
from shoal.models.user import User
from shoal.payloads import (
    ApplicationCommandOptionChoice,
    InteractionType,
    MessageFlags,
    Permissions,
)
from shoal.payloads.interactions import InteractionResponse as ResponsePayload
from shoal.rest.errors import HTTPError
from shoal.rest.files import File
from tests.support.client import started
from tests.support.fakes import FakeTransport
from tests.support.interactions import (
    TOKEN,
    PersistentView,
    RecordingModal,
    autocomplete,
    command,
    component,
    modal_submit,
    payload,
)
from tests.support.models import ALICE, APPLICATION, GENERAL, GUILD, ROW_VIEW, message
from tests.support.rest import API

CALLBACK = f"/interactions/900/{TOKEN}/callback"
WEBHOOK = f"/webhooks/{APPLICATION}/{TOKEN}"
MESSAGE_ID = 4321


def created(message_id: int) -> dict[str, object]:
    """What Create Interaction Response returns with `with_response=true` for a new message."""
    return {
        "interaction": {"id": "900", "type": 2, "response_message_id": str(message_id)},
        "resource": {"type": 4, "message": message(message_id)},
    }


async def receive(data: dict[str, object]) -> tuple[Client, FakeTransport, Interaction]:
    client, transport = await started()
    interaction = await client.process_interaction(payload(data))
    return client, transport, interaction


def last(transport: FakeTransport) -> tuple[str, str, object]:
    """The last request as `(method, path, JSON body)`; a multipart body reads as `None`."""
    request = transport.requests[-1]
    multipart = request.headers.get("Content-Type", "").startswith("multipart")
    body = msgspec.json.decode(request.body) if request.body and not multipart else None
    return request.method, request.url.removeprefix(API), body


async def test_an_interaction_in_a_guild() -> None:
    _, _, interaction = await receive(command("ping"))
    assert interaction.type is InteractionType.APPLICATION_COMMAND
    assert interaction.id == 900
    assert interaction.application_id == APPLICATION
    assert interaction.guild_id == GUILD
    assert interaction.guild is not None
    assert interaction.channel_id == GENERAL
    assert isinstance(interaction.channel, TextChannel)
    assert isinstance(interaction.user, Member)
    assert interaction.user.display_name == "Ally"
    assert interaction.message is None
    assert interaction.locale == "en-GB"
    assert interaction.guild_locale == "en-US"
    assert interaction.permissions == Permissions(send_messages=True)
    assert interaction.app_permissions == 442368
    assert interaction.entitlements == []
    assert interaction.token == TOKEN
    assert interaction.expires_at - interaction.created_at == timedelta(minutes=15)
    assert interaction.is_expired()  # its ID is from 1970
    assert interaction.command is interaction.namespace is None
    assert repr(interaction) == "<Interaction id=900 type=APPLICATION_COMMAND>"
    assert TOKEN not in repr(interaction.payload)


async def test_an_interaction_in_dms() -> None:
    _, _, interaction = await receive(command("ping", in_guild=False))
    assert interaction.guild_id is None
    assert interaction.guild is None
    assert isinstance(interaction.user, User)
    assert interaction.permissions == Permissions.none()


async def test_send_message_answers_once() -> None:
    _, transport, interaction = await receive(command("ping"))
    transport.queue(200, created(MESSAGE_ID))
    await interaction.response.send_message("pong", ephemeral=True, embed=Embed(title="t"), view=ROW_VIEW)
    assert interaction.response.is_done()
    method, path, body = last(transport)
    assert (method, path) == ("POST", CALLBACK + "?with_response=true")
    assert body == {
        "type": 4,
        "data": {
            "content": "pong",
            "embeds": [{"title": "t"}],
            "flags": int(MessageFlags(ephemeral=True)),
            "components": [
                {"type": 1, "components": [{"type": 2, "style": 1, "custom_id": "ok", "label": "OK"}]}
            ],
        },
    }
    with pytest.raises(InteractionRespondedError, match="already been responded"):
        await interaction.response.send_message("again")


async def test_a_view_sent_in_a_response_answers_only_on_its_message() -> None:
    client, transport, interaction = await receive(command("vote"))
    view = PersistentView(persistent=False)
    transport.queue(200, created(MESSAGE_ID))
    await interaction.response.send_message("vote", view=view)
    elsewhere = await client.process_interaction(payload(component("persistent:ok", message_id=1)))
    here = await client.process_interaction(payload(component("persistent:ok", message_id=MESSAGE_ID)))
    assert view.received == [(here, "persistent:ok")]
    assert elsewhere.response.is_done() is False


async def test_a_failed_response_can_be_sent_again() -> None:
    _, transport, interaction = await receive(command("ping"))
    transport.queue(400, {"code": 50035, "message": "Invalid Form Body"})
    with pytest.raises(HTTPError):
        await interaction.response.send_message("pong")
    assert not interaction.response.is_done()
    transport.queue(204)
    await interaction.response.send_message("pong")
    assert interaction.response.is_done()


async def test_a_second_response_while_the_first_is_in_flight_is_refused() -> None:
    _, transport, interaction = await receive(command("ping"))
    transport.queue(204)
    first = asyncio.create_task(interaction.response.send_message("pong"))
    await asyncio.sleep(0)
    with pytest.raises(InteractionRespondedError):
        await interaction.response.defer()
    await first


async def test_defer_shows_thinking_for_commands_and_nothing_for_components() -> None:
    _, transport, interaction = await receive(command("slow"))
    transport.queue(204)
    await interaction.response.defer(ephemeral=True)
    assert last(transport)[2] == {"type": 5, "data": {"flags": int(MessageFlags(ephemeral=True))}}
    _, transport, pressed = await receive(component("x"))
    transport.queue(204)
    await pressed.response.defer()
    assert last(transport)[2] == {"type": 6}
    _, transport, thinking = await receive(component("x"))
    transport.queue(204)
    await thinking.response.defer(thinking=True)
    assert last(transport)[2] == {"type": 5, "data": {}}
    _, _, suggesting = await receive(autocomplete("ping"))
    with pytest.raises(TypeError, match="cannot be deferred"):
        await suggesting.response.defer()
    # A modal opened by a command has no message to update.
    _, transport, submitted = await receive(modal_submit("form"))
    transport.queue(204)
    await submitted.response.defer()
    assert last(transport)[2] == {"type": 5, "data": {}}


async def test_edit_message_updates_the_components_message() -> None:
    _, transport, interaction = await receive(component("x", message_id=77))
    assert interaction.message is not None
    assert interaction.message.id == 77
    transport.queue(204)
    await interaction.response.edit_message(content="done", view=None)
    assert last(transport)[2] == {"type": 7, "data": {"content": "done", "components": []}}


async def test_modals_autocomplete_and_activities() -> None:
    client, transport, interaction = await receive(command("form"))
    modal = RecordingModal()
    transport.queue(204)
    await interaction.response.send_modal(modal)
    method, path, body = last(transport)
    assert (method, path) == ("POST", CALLBACK)
    assert isinstance(body, dict)
    assert body["type"] == 9
    assert await client.view_store.dispatch_modal(interaction, "form", ALICE)
    _, transport, typing = await receive(
        autocomplete("card", {"type": 3, "name": "name", "value": "Gi", "focused": True})
    )
    transport.queue(204)
    await typing.response.autocomplete([ApplicationCommandOptionChoice(name="Gitrog", value="gitrog")])
    assert last(transport)[2] == {"type": 8, "data": {"choices": [{"name": "Gitrog", "value": "gitrog"}]}}
    _, transport, activity = await receive(command("play"))
    transport.queue(204)
    await activity.response.launch_activity()
    assert last(transport)[2] == {"type": 12}


async def test_followups_and_the_original_response() -> None:
    _, transport, interaction = await receive(command("ping"))
    transport.queue(200, message(5))
    sent = await interaction.followup.send("more", ephemeral=True, view=ROW_VIEW, file=File("a.txt", b"a"))
    assert sent.id == 5
    assert transport.requests[-1].url == f"{API}{WEBHOOK}"
    transport.queue(200, message(5))
    assert (await interaction.followup.fetch_message(5)).id == 5
    transport.queue(200, message(5, content="edited"))
    edited = await interaction.followup.edit_message(5, content="edited", view=ROW_VIEW)
    assert edited.content == "edited"
    transport.queue(204)
    await interaction.followup.delete_message(5)
    assert last(transport)[:2] == ("DELETE", f"{WEBHOOK}/messages/5")
    transport.queue(200, message(6))
    assert (await interaction.original_response()).id == 6
    transport.queue(200, message(6, content="final"))
    final = await interaction.edit_original_response(content="final", view=ROW_VIEW)
    assert final.content == "final"
    assert last(transport)[:2] == ("PATCH", f"{WEBHOOK}/messages/@original")
    transport.queue(204)
    await interaction.delete_original_response()
    assert last(transport)[:2] == ("DELETE", f"{WEBHOOK}/messages/@original")


async def test_delete_after_removes_the_response() -> None:
    _, transport, interaction = await receive(command("ping"))
    transport.queue(204)
    transport.queue(204)
    await interaction.response.send_message("brief", delete_after=0)
    for _ in range(5):
        await asyncio.sleep(0)
    assert last(transport)[:2] == ("DELETE", f"{WEBHOOK}/messages/@original")


async def test_a_responder_replaces_the_callback_request() -> None:
    client, transport = await started()
    sent: list[tuple[ResponsePayload, Sequence[File]]] = []

    async def responder(response: ResponsePayload, files: Sequence[File]) -> None:
        sent.append((response, files))

    before = len(transport.requests)
    interaction = await client.process_interaction(payload(command("ping")), responder=responder)
    await interaction.response.send_message("inline")
    assert len(sent) == 1
    assert len(transport.requests) == before


async def test_components_reach_their_view() -> None:
    client, _ = await started()
    view = PersistentView()
    client.add_view(view)
    interaction = await client.process_interaction(payload(component("persistent:ok", message_id=12)))
    assert view.received == [(interaction, "persistent:ok")]
