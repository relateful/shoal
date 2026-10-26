from datetime import UTC, datetime
from typing import cast

import pytest

from shoal.cache.store import CacheStore
from shoal.cache.updater import CacheUpdater
from shoal.client.events import EventTranslator
from shoal.models.base import Object
from shoal.models.channel import TextChannel, VoiceChannel
from shoal.models.emoji import Emoji
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.message import Message, Reaction
from shoal.models.role import Role
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads import DISPATCH_PAYLOADS, MessageDelete, StatusType, VoiceState
from tests.support.client import Recorder, feed, started
from tests.support.dispatches import DISPATCH_SAMPLES
from tests.support.models import (
    ALICE,
    BOB,
    BOT,
    GENERAL,
    GUILD,
    MODS,
    VOICE,
    World,
    channel,
    guild_create,
    member,
    message,
    role,
    user,
)

GUILD_ID = str(GUILD)

type Json = dict[str, object]


def ignore(*args: object) -> None:
    del args


def test_every_documented_dispatch_is_translated_or_handled_by_the_client() -> None:
    world = World()
    translator = EventTranslator(world.state, CacheUpdater(CacheStore()), ignore)
    # The client handles READY (readiness) itself; INTERACTION_CREATE and RESUMED have no entry in
    # DISPATCH_PAYLOADS and are handled by the client too.
    assert set(DISPATCH_PAYLOADS) - translator.handles == {"READY"}


async def test_a_new_guild_is_joined_and_a_known_one_becomes_available() -> None:
    client, _ = await started()
    events = Recorder(
        client, "guild_join", "guild_available", "guild_unavailable", "guild_remove", "guild_update"
    )
    await feed(client, "GUILD_CREATE", guild_create() | {"id": "11"})
    await feed(client, "GUILD_DELETE", {"id": "11", "unavailable": True})
    await feed(client, "GUILD_CREATE", guild_create() | {"id": "11"})
    await feed(
        client,
        "GUILD_UPDATE",
        {k: v for k, v in guild_create().items() if k != "members"} | {"id": "11", "name": "Renamed"},
    )
    await feed(client, "GUILD_DELETE", {"id": "11"})
    assert events.names() == [
        "guild_join",
        "guild_unavailable",
        "guild_available",
        "guild_update",
        "guild_remove",
    ]
    before, after = events.args("guild_update")
    assert isinstance(before, Guild)
    assert isinstance(after, Guild)
    assert (before.name, after.name) == ("Shoal Test", "Renamed")
    [gone] = events.args("guild_remove")
    assert isinstance(gone, Guild)
    # The cache forgot it, but the guild handed over still has what it had.
    assert client.get_guild(11) is None
    assert gone.channels
    assert gone.members
    assert gone.roles
    await feed(client, "GUILD_DELETE", {"id": "12"})  # never cached: nothing to report
    assert len(events.seen) == 5


async def test_messages_and_their_edits_and_deletions() -> None:
    client, _ = await started()
    events = Recorder(
        client,
        "message",
        "message_edit",
        "raw_message_edit",
        "message_delete",
        "raw_message_delete",
        "bulk_message_delete",
        "raw_bulk_message_delete",
    )
    await feed(client, "MESSAGE_CREATE", message(5) | {"guild_id": GUILD_ID})
    [created] = events.args("message")
    assert isinstance(created, Message)
    assert isinstance(created.author, Member)
    await feed(client, "MESSAGE_UPDATE", message(5, content="edited") | {"guild_id": GUILD_ID})
    before, after = events.args("message_edit")
    assert isinstance(before, Message)
    assert isinstance(after, Message)
    assert (before.content, after.content) == ("hello", "edited")
    await feed(client, "MESSAGE_UPDATE", message(6) | {"guild_id": GUILD_ID})  # not cached: raw only
    assert events.names().count("raw_message_edit") == 2
    assert events.names().count("message_edit") == 1
    await feed(client, "MESSAGE_DELETE", {"id": "5", "channel_id": str(GENERAL), "guild_id": GUILD_ID})
    [deleted] = events.args("message_delete")
    assert isinstance(deleted, Message)
    [raw] = events.args("raw_message_delete")
    assert isinstance(raw, MessageDelete)
    await feed(client, "MESSAGE_CREATE", message(7) | {"guild_id": GUILD_ID})
    await feed(
        client, "MESSAGE_DELETE_BULK", {"ids": ["7", "8"], "channel_id": str(GENERAL), "guild_id": GUILD_ID}
    )
    [bulk] = events.args("bulk_message_delete")
    assert isinstance(bulk, list)
    assert [found.id for found in cast("list[Message]", bulk)] == [7]  # event arguments are objects
    assert "raw_bulk_message_delete" in events.names()


async def test_removing_the_last_reaction_reports_it_at_zero() -> None:
    client, _ = await started()
    events = Recorder(client, "reaction_remove")
    await feed(client, "MESSAGE_CREATE", message(6) | {"guild_id": GUILD_ID})
    fire = {"id": None, "name": "\N{FIRE}"}
    use: Json = {"channel_id": str(GENERAL), "message_id": "6", "guild_id": GUILD_ID, "user_id": str(ALICE)}
    await feed(client, "MESSAGE_REACTION_ADD", use | {"emoji": fire, "burst": False, "type": 0})
    await feed(client, "MESSAGE_REACTION_REMOVE", use | {"emoji": fire, "burst": False, "type": 0})
    removed, _ = events.args("reaction_remove")
    assert isinstance(removed, Reaction)
    assert (removed.count, removed.normal_count, removed.emoji) == (0, 0, "\N{FIRE}")


async def test_reactions_on_cached_messages() -> None:
    client, _ = await started()
    events = Recorder(
        client,
        "reaction_add",
        "raw_reaction_add",
        "reaction_remove",
        "raw_reaction_remove",
        "reaction_clear",
        "raw_reaction_clear",
        "reaction_clear_emoji",
        "raw_reaction_clear_emoji",
    )
    await feed(client, "MESSAGE_CREATE", message(5) | {"guild_id": GUILD_ID})
    fire = {"id": None, "name": "\N{FIRE}"}
    base: Json = {"channel_id": str(GENERAL), "message_id": "5", "guild_id": GUILD_ID}
    await feed(
        client,
        "MESSAGE_REACTION_ADD",
        base | {"user_id": str(ALICE), "emoji": fire, "burst": False, "type": 0},
    )
    reaction, who = events.args("reaction_add")
    assert isinstance(reaction, Reaction)
    assert reaction.emoji == "\N{FIRE}"
    assert reaction.count == 1
    assert isinstance(who, Member)
    await feed(
        client, "MESSAGE_REACTION_ADD", base | {"user_id": str(BOB), "emoji": fire, "burst": False, "type": 0}
    )
    await feed(
        client,
        "MESSAGE_REACTION_REMOVE",
        base | {"user_id": str(BOB), "emoji": fire, "burst": False, "type": 0},
    )
    removed, _ = events.args("reaction_remove")
    assert isinstance(removed, Reaction)
    assert removed.count == 1
    await feed(client, "MESSAGE_REACTION_REMOVE_EMOJI", base | {"emoji": fire})
    [cleared] = events.args("reaction_clear_emoji")
    assert isinstance(cleared, Reaction)
    await feed(
        client,
        "MESSAGE_REACTION_ADD",
        base | {"user_id": str(ALICE), "emoji": fire, "burst": False, "type": 0},
    )
    await feed(client, "MESSAGE_REACTION_REMOVE_ALL", base)
    found, reactions = events.args("reaction_clear")
    assert isinstance(found, Message)
    assert isinstance(reactions, list)
    assert len(cast("list[Reaction]", reactions)) == 1  # event arguments are objects
    unknown = base | {"message_id": "99", "user_id": str(ALICE), "emoji": fire, "burst": False, "type": 0}
    await feed(client, "MESSAGE_REACTION_ADD", unknown)
    assert events.names().count("raw_reaction_add") == 4
    assert events.names().count("reaction_add") == 3


async def test_members_join_update_and_leave() -> None:
    client, _ = await started()
    events = Recorder(
        client, "member_join", "member_update", "raw_member_update", "member_remove", "raw_member_remove"
    )
    await feed(client, "GUILD_MEMBER_ADD", member(8, "newbie") | {"guild_id": GUILD_ID})
    [joined] = events.args("member_join")
    assert isinstance(joined, Member)
    update: Json = {
        "guild_id": GUILD_ID,
        "roles": [str(MODS)],
        "user": user(8, "newbie"),
        "avatar": None,
        "banner": None,
        "joined_at": None,
        "nick": "Newb",
    }
    await feed(client, "GUILD_MEMBER_UPDATE", update)
    before, after = events.args("member_update")
    assert isinstance(before, Member)
    assert isinstance(after, Member)
    assert (before.nick, after.nick) == (None, "Newb")
    await feed(client, "GUILD_MEMBER_REMOVE", {"guild_id": GUILD_ID, "user": user(8, "newbie")})
    [left] = events.args("member_remove")
    assert isinstance(left, Member)
    await feed(client, "GUILD_MEMBER_REMOVE", {"guild_id": GUILD_ID, "user": user(9, "ghost")})
    assert events.names().count("raw_member_remove") == 2
    assert events.names().count("member_remove") == 1


async def test_a_member_update_before_their_join_still_reports_the_join() -> None:
    # AutoMod quarantine sends GUILD_MEMBER_UPDATE before GUILD_MEMBER_ADD.
    client, _ = await started()
    events = Recorder(client, "member_join", "raw_member_update")
    update: Json = {
        "guild_id": GUILD_ID,
        "roles": [],
        "user": user(8, "q"),
        "avatar": None,
        "banner": None,
        "joined_at": None,
    }
    await feed(client, "GUILD_MEMBER_UPDATE", update)
    await feed(client, "GUILD_MEMBER_ADD", member(8, "q") | {"guild_id": GUILD_ID})
    assert events.names() == ["raw_member_update", "member_join"]


async def test_bans_presences_and_users() -> None:
    client, _ = await started()
    events = Recorder(
        client, "member_ban", "member_unban", "presence_update", "raw_presence_update", "user_update"
    )
    await feed(client, "GUILD_BAN_ADD", {"guild_id": GUILD_ID, "user": user(9, "spammer")})
    await feed(client, "GUILD_BAN_REMOVE", {"guild_id": GUILD_ID, "user": user(9, "spammer")})
    guild, banned = events.args("member_ban")
    assert isinstance(guild, Guild)
    assert isinstance(banned, User)
    presence: Json = {
        "user": {"id": str(ALICE)},
        "status": "online",
        "activities": [],
        "client_status": {"desktop": "online"},
        "guild_id": GUILD_ID,
    }
    await feed(client, "PRESENCE_UPDATE", presence)
    before, after = events.args("presence_update")
    assert isinstance(before, Member)
    assert isinstance(after, Member)
    assert (before.status, after.status) == (StatusType.IDLE, StatusType.ONLINE)
    await feed(client, "USER_UPDATE", user(BOT, "renamed"))
    old, new = events.args("user_update")
    assert isinstance(old, User)
    assert isinstance(new, User)
    assert (old.name, new.name) == ("shoalbot", "renamed")


async def test_roles_emojis_and_stickers() -> None:
    client, _ = await started()
    events = Recorder(
        client,
        "guild_role_create",
        "guild_role_update",
        "guild_role_delete",
        "guild_emojis_update",
        "guild_stickers_update",
    )
    await feed(client, "GUILD_ROLE_CREATE", {"guild_id": GUILD_ID, "role": role(30, "new", position=3)})
    await feed(client, "GUILD_ROLE_UPDATE", {"guild_id": GUILD_ID, "role": role(30, "renamed", position=3)})
    await feed(client, "GUILD_ROLE_DELETE", {"guild_id": GUILD_ID, "role_id": "30"})
    [created] = events.args("guild_role_create")
    before, after = events.args("guild_role_update")
    [deleted] = events.args("guild_role_delete")
    assert isinstance(created, Role)
    assert isinstance(before, Role)
    assert isinstance(after, Role)
    assert (before.name, after.name) == ("new", "renamed")
    assert isinstance(deleted, Role)
    await feed(client, "GUILD_EMOJIS_UPDATE", {"guild_id": GUILD_ID, "emojis": []})
    _, old_emojis, new_emojis = events.args("guild_emojis_update")
    assert isinstance(old_emojis, list)
    # Event arguments are objects.
    assert [type(emoji) for emoji in cast("list[object]", old_emojis)] == [Emoji]
    assert new_emojis == []
    await feed(client, "GUILD_STICKERS_UPDATE", {"guild_id": GUILD_ID, "stickers": []})
    assert events.args("guild_stickers_update")[1:] == ([], [])


async def test_channels_and_threads() -> None:
    client, _ = await started()
    events = Recorder(
        client,
        "guild_channel_create",
        "guild_channel_update",
        "guild_channel_delete",
        "guild_channel_pins_update",
        "thread_create",
        "thread_join",
        "thread_update",
        "thread_delete",
        "raw_thread_delete",
        "webhooks_update",
        "private_channel_create",
    )
    await feed(client, "CHANNEL_CREATE", channel(60, 0, "new"))
    await feed(client, "CHANNEL_UPDATE", channel(60, 0, "renamed"))
    await feed(
        client,
        "CHANNEL_PINS_UPDATE",
        {"guild_id": GUILD_ID, "channel_id": "60", "last_pin_timestamp": "2024-01-01T00:00:00+00:00"},
    )
    await feed(client, "CHANNEL_DELETE", channel(60, 0, "renamed"))
    [created] = events.args("guild_channel_create")
    before, after = events.args("guild_channel_update")
    assert isinstance(created, TextChannel)
    assert isinstance(before, TextChannel)
    assert isinstance(after, TextChannel)
    assert (before.name, after.name) == ("new", "renamed")
    _, pinned_at = events.args("guild_channel_pins_update")
    assert pinned_at == datetime(2024, 1, 1, tzinfo=UTC)
    await feed(client, "CHANNEL_CREATE", {"id": "61", "type": 1, "recipients": [user(ALICE, "alice")]})
    assert "private_channel_create" in events.names()
    thread: Json = channel(62, 11, "t", parent=GENERAL)
    await feed(client, "THREAD_CREATE", thread | {"newly_created": True})
    await feed(client, "THREAD_CREATE", channel(63, 12, "invited", parent=GENERAL))
    await feed(client, "THREAD_UPDATE", thread | {"name": "renamed"})
    await feed(
        client, "THREAD_DELETE", {"id": "62", "guild_id": GUILD_ID, "parent_id": str(GENERAL), "type": 11}
    )
    assert isinstance(events.args("thread_create")[0], Thread)
    assert isinstance(events.args("thread_join")[0], Thread)
    old, new = events.args("thread_update")
    assert isinstance(old, Thread)
    assert isinstance(new, Thread)
    assert new.name == "renamed"
    assert isinstance(events.args("thread_delete")[0], Thread)
    await feed(client, "WEBHOOKS_UPDATE", {"guild_id": GUILD_ID, "channel_id": str(GENERAL)})
    assert isinstance(events.args("webhooks_update")[0], TextChannel)


async def test_typing_and_voice() -> None:
    client, _ = await started()
    events = Recorder(client, "typing", "raw_typing", "voice_state_update")
    await feed(
        client,
        "TYPING_START",
        {
            "channel_id": str(GENERAL),
            "guild_id": GUILD_ID,
            "user_id": str(ALICE),
            "timestamp": 1704067200,
            "member": member(ALICE, "alice"),
        },
    )
    where, who, when = events.args("typing")
    assert isinstance(where, TextChannel)
    assert isinstance(who, Member)
    assert when == datetime(2024, 1, 1, tzinfo=UTC)
    state: Json = {
        "guild_id": GUILD_ID,
        "channel_id": None,
        "user_id": str(BOB),
        "session_id": "s",
        "deaf": False,
        "mute": False,
        "self_deaf": False,
        "self_mute": False,
        "self_video": False,
        "suppress": False,
        "request_to_speak_timestamp": None,
    }
    await feed(client, "VOICE_STATE_UPDATE", state)
    who, before, after = events.args("voice_state_update")
    assert isinstance(who, Member)
    assert isinstance(before, VoiceState)
    assert before.channel_id == VOICE
    assert after is None
    assert isinstance(client.get_channel(VOICE), VoiceChannel)


@pytest.mark.parametrize(
    ("dispatch", "event"),
    [
        ("AUTO_MODERATION_ACTION_EXECUTION", "automod_action"),
        ("AUTO_MODERATION_RULE_CREATE", "automod_rule_create"),
        ("ENTITLEMENT_CREATE", "entitlement_create"),
        ("GUILD_AUDIT_LOG_ENTRY_CREATE", "audit_log_entry_create"),
        ("INTEGRATION_CREATE", "integration_create"),
        ("INVITE_CREATE", "invite_create"),
        ("MESSAGE_POLL_VOTE_ADD", "raw_poll_vote_add"),
        ("SUBSCRIPTION_UPDATE", "subscription_update"),
        ("VOICE_SERVER_UPDATE", "voice_server_update"),
    ],
)
async def test_events_without_models_carry_their_payload(dispatch: str, event: str) -> None:
    client, _ = await started()
    events = Recorder(client, event)
    await feed(client, dispatch, DISPATCH_SAMPLES[dispatch])
    [payload] = events.args(event)
    assert isinstance(payload, DISPATCH_PAYLOADS[dispatch])


async def test_scheduled_events_stages_and_sounds() -> None:
    client, _ = await started()
    events = Recorder(
        client,
        "scheduled_event_create",
        "scheduled_event_update",
        "scheduled_event_user_add",
        "scheduled_event_user_remove",
        "scheduled_event_delete",
        "stage_instance_update",
        "stage_instance_delete",
        "soundboard_sound_create",
        "soundboard_sound_update",
        "soundboard_sound_delete",
        "integration_create",
    )
    scheduled: Json = DISPATCH_SAMPLES["GUILD_SCHEDULED_EVENT_CREATE"] | {"guild_id": GUILD_ID}
    await feed(client, "GUILD_SCHEDULED_EVENT_CREATE", scheduled)
    await feed(client, "GUILD_SCHEDULED_EVENT_UPDATE", scheduled | {"name": "Moved"})
    subscription: Json = {
        "guild_scheduled_event_id": scheduled["id"],
        "user_id": str(ALICE),
        "guild_id": GUILD_ID,
    }
    await feed(client, "GUILD_SCHEDULED_EVENT_USER_ADD", subscription)
    await feed(client, "GUILD_SCHEDULED_EVENT_USER_REMOVE", subscription)
    await feed(client, "GUILD_SCHEDULED_EVENT_DELETE", scheduled)
    assert events.names()[:5] == [
        "scheduled_event_create",
        "scheduled_event_update",
        "scheduled_event_user_add",
        "scheduled_event_user_remove",
        "scheduled_event_delete",
    ]
    _, subscriber = events.args("scheduled_event_user_add")
    assert isinstance(subscriber, Member)
    stage: Json = {
        "id": "50",
        "guild_id": GUILD_ID,
        "channel_id": "43",
        "topic": "Q&A",
        "privacy_level": 2,
        "discoverable_disabled": False,
        "guild_scheduled_event_id": None,
    }
    await feed(client, "STAGE_INSTANCE_UPDATE", stage)
    await feed(client, "STAGE_INSTANCE_DELETE", stage)
    before, after = events.args("stage_instance_update")
    assert (getattr(before, "topic", None), getattr(after, "topic", None)) == ("Town hall", "Q&A")
    sound: Json = {
        "name": "q",
        "sound_id": "7",
        "volume": 1.0,
        "emoji_id": None,
        "emoji_name": None,
        "guild_id": GUILD_ID,
        "available": True,
    }
    await feed(client, "GUILD_SOUNDBOARD_SOUND_CREATE", sound)
    await feed(client, "GUILD_SOUNDBOARD_SOUND_UPDATE", sound | {"name": "r"})
    await feed(client, "GUILD_SOUNDBOARD_SOUND_DELETE", {"sound_id": "7", "guild_id": GUILD_ID})
    assert events.names()[-3:] == [
        "soundboard_sound_create",
        "soundboard_sound_update",
        "soundboard_sound_delete",
    ]
    assert Object(1) == Object(1)


async def test_events_in_an_uncached_guild_are_not_dropped() -> None:
    client, _ = await started()
    events = Recorder(client, "message", "member_join", "member_ban")
    await feed(client, "MESSAGE_CREATE", message(5, channel_id=999) | {"guild_id": "555"})
    await feed(client, "GUILD_MEMBER_ADD", member(8, "x") | {"guild_id": "555"})
    await feed(client, "GUILD_BAN_ADD", {"guild_id": "555", "user": user(9, "y")})
    assert events.names() == ["message", "member_join", "member_ban"]
    guild, _ = events.args("member_ban")
    assert guild == Object(555)
