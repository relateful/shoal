import logging
from pathlib import Path

import msgspec
import pytest

from shoal.cache.store import CacheStore
from shoal.cache.updater import CacheUpdater
from shoal.core.dispatch import DispatchEvent
from shoal.core.snowflake import Snowflake
from shoal.payloads import DISPATCH_PAYLOADS, Intents
from tests.support.fakes import FakeClock

GUILD_ID = 10
SELF_ID = 1

type Json = dict[str, object]


def user(user_id: int, name: str = "user") -> Json:
    return {"id": str(user_id), "username": name, "discriminator": "0", "global_name": None, "avatar": None}


def member(user_id: int, *, nick: str | None = None) -> Json:
    return {
        "user": user(user_id),
        "nick": nick,
        "roles": [],
        "joined_at": "2024-01-01T00:00:00+00:00",
        "deaf": False,
        "mute": False,
        "flags": 0,
    }


def channel(channel_id: int, *, kind: int = 0, parent: int | None = None) -> Json:
    return {
        "id": str(channel_id),
        "type": kind,
        "guild_id": str(GUILD_ID),
        "parent_id": str(parent) if parent else None,
    }


def role(role_id: int) -> Json:
    return {
        "id": str(role_id),
        "name": "r",
        "color": 0,
        "colors": {"primary_color": 0, "secondary_color": None, "tertiary_color": None},
        "hoist": False,
        "position": 0,
        "permissions": "0",
        "managed": False,
        "mentionable": False,
        "flags": 0,
    }


def voice_state(user_id: int, channel_id: int | None) -> Json:
    return {
        "channel_id": str(channel_id) if channel_id else None,
        "user_id": str(user_id),
        "session_id": "s",
        "deaf": False,
        "mute": False,
        "self_deaf": False,
        "self_mute": False,
        "self_video": False,
        "suppress": False,
        "request_to_speak_timestamp": None,
    }


def presence(user_id: int, status: str = "online") -> Json:
    return {
        "user": {"id": str(user_id)},
        "status": status,
        "activities": [],
        "client_status": {"desktop": status},
    }


def guild_create(**extra: object) -> Json:
    guild: Json = {
        "id": str(GUILD_ID),
        "name": "g",
        "owner_id": "1",
        "afk_timeout": 0,
        "roles": [role(20)],
        "emojis": [{"id": "30", "name": "e"}],
        "features": [],
        "preferred_locale": "en-US",
        "premium_progress_bar_enabled": False,
        "joined_at": "2024-01-01T00:00:00+00:00",
        "large": False,
        "member_count": 1,
        "members": [member(2)],
        "channels": [channel(40)],
        "threads": [],
        "voice_states": [voice_state(2, 40)],
        "presences": [presence(2)],
    }
    for key in (
        "icon", "splash", "discovery_splash", "afk_channel_id", "application_id", "system_channel_id",
        "rules_channel_id", "vanity_url_code", "description", "banner", "public_updates_channel_id",
        "safety_alerts_channel_id",
    ):  # fmt: skip
        guild[key] = None
    for key in (
        "verification_level", "default_message_notifications", "explicit_content_filter", "mfa_level",
        "system_channel_flags", "premium_tier", "nsfw_level",
    ):  # fmt: skip
        guild[key] = 0
    return guild | extra


def message(message_id: int, **extra: object) -> Json:
    base: Json = {
        "id": str(message_id),
        "channel_id": "40",
        "guild_id": str(GUILD_ID),
        "author": user(2),
        "content": "hi",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "edited_timestamp": None,
        "tts": False,
        "mention_everyone": False,
        "mentions": [],
        "mention_roles": [],
        "attachments": [],
        "embeds": [],
        "pinned": False,
        "type": 0,
    }
    return base | extra


def ready() -> Json:
    return {
        "v": 10,
        "user": user(SELF_ID, "bot"),
        "guilds": [{"id": str(GUILD_ID), "unavailable": True}],
        "session_id": "s",
        "resume_gateway_url": "wss://r",
        "application": {"id": "3", "flags": 0},
    }


class Harness:
    def __init__(self, intents: Intents | None = None) -> None:
        self.store = CacheStore(clock=FakeClock())
        self.updater = CacheUpdater(self.store, intents=intents or Intents(guild_presences=True))

    async def send(self, name: str, data: object, *, shard: int = 0, sequence: int | None = None) -> None:
        raw = msgspec.Raw(msgspec.json.encode(data))
        await self.updater.apply(DispatchEvent(shard, name, sequence, raw))

    async def started(self) -> "Harness":
        await self.send("READY", ready())
        await self.send("GUILD_CREATE", guild_create())
        return self


async def test_handled_events_are_pinned() -> None:
    assert CacheUpdater(CacheStore()).handled_events == {
        "CHANNEL_CREATE", "CHANNEL_DELETE", "CHANNEL_PINS_UPDATE", "CHANNEL_UPDATE",
        "GUILD_CREATE", "GUILD_DELETE", "GUILD_EMOJIS_UPDATE", "GUILD_MEMBERS_CHUNK", "GUILD_MEMBER_ADD",
        "GUILD_MEMBER_REMOVE", "GUILD_MEMBER_UPDATE", "GUILD_ROLE_CREATE", "GUILD_ROLE_DELETE",
        "GUILD_ROLE_UPDATE", "GUILD_UPDATE",
        "GUILD_SCHEDULED_EVENT_CREATE", "GUILD_SCHEDULED_EVENT_DELETE", "GUILD_SCHEDULED_EVENT_UPDATE",
        "GUILD_SCHEDULED_EVENT_USER_ADD", "GUILD_SCHEDULED_EVENT_USER_REMOVE",
        "GUILD_SOUNDBOARD_SOUNDS_UPDATE", "GUILD_SOUNDBOARD_SOUND_CREATE", "GUILD_SOUNDBOARD_SOUND_DELETE",
        "GUILD_SOUNDBOARD_SOUND_UPDATE", "GUILD_STICKERS_UPDATE",
        "MESSAGE_CREATE", "MESSAGE_DELETE", "MESSAGE_DELETE_BULK", "MESSAGE_POLL_VOTE_ADD",
        "MESSAGE_POLL_VOTE_REMOVE", "MESSAGE_REACTION_ADD",
        "MESSAGE_REACTION_REMOVE", "MESSAGE_REACTION_REMOVE_ALL", "MESSAGE_REACTION_REMOVE_EMOJI",
        "MESSAGE_UPDATE",
        "PRESENCE_UPDATE", "READY", "RESUMED", "SOUNDBOARD_SOUNDS",
        "STAGE_INSTANCE_CREATE", "STAGE_INSTANCE_DELETE", "STAGE_INSTANCE_UPDATE",
        "THREAD_CREATE", "THREAD_DELETE", "THREAD_LIST_SYNC", "THREAD_MEMBERS_UPDATE", "THREAD_MEMBER_UPDATE",
        "THREAD_UPDATE",
        "USER_UPDATE", "VOICE_STATE_UPDATE",
    }  # fmt: skip


async def test_every_handled_event_is_a_documented_dispatch() -> None:
    handled = CacheUpdater(CacheStore()).handled_events
    assert handled - set(DISPATCH_PAYLOADS) == {"RESUMED"}


async def test_guild_create_fills_every_kind() -> None:
    harness = await Harness().started()
    store = harness.store
    guild = await store.get_guild(GUILD_ID)
    assert guild is not None
    assert guild.roles == []
    assert await store.get_role(20) is not None
    assert await store.get_emoji(30) is not None
    assert await store.get_channel(40) is not None
    assert await store.get_member(GUILD_ID, 2) is not None
    assert await store.get_user(2) is not None
    assert await store.get_user(SELF_ID) is not None
    assert await store.get_voice_state(GUILD_ID, 2) is not None
    assert await store.get_presence(GUILD_ID, 2) is not None


async def test_unavailable_guild_create_keeps_cached_data() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_CREATE", {"id": str(GUILD_ID), "unavailable": True})
    assert await harness.store.get_channel(40) is not None


async def test_undecodable_events_are_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    harness = await Harness().started()
    with caplog.at_level(logging.ERROR, logger="shoal.cache"):
        await harness.send("GUILD_CREATE", {"id": str(GUILD_ID)})
    assert "could not decode GUILD_CREATE" in caplog.text
    assert await harness.store.get_channel(40) is not None


async def test_guild_delete_forgets_only_when_removed() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_DELETE", {"id": str(GUILD_ID), "unavailable": True})
    assert await harness.store.get_guild(GUILD_ID) is not None
    await harness.send("GUILD_DELETE", {"id": str(GUILD_ID)})
    assert await harness.store.get_guild(GUILD_ID) is None
    assert await harness.store.get_channel(40) is None
    assert await harness.store.get_member(GUILD_ID, 2) is None


async def test_reconnect_with_a_new_session_drops_what_disappeared() -> None:
    harness = await Harness().started()
    await harness.send("READY", ready())
    await harness.send(
        "GUILD_CREATE", guild_create(channels=[channel(41)], members=[], voice_states=[], presences=[])
    )
    assert await harness.store.get_channel(40) is None
    assert await harness.store.get_channel(41) is not None
    assert await harness.store.get_member(GUILD_ID, 2) is None
    assert await harness.store.get_voice_state(GUILD_ID, 2) is None


async def test_channel_events() -> None:
    harness = await Harness().started()
    await harness.send("CHANNEL_UPDATE", channel(40) | {"name": "renamed"})
    updated = await harness.store.get_channel(40)
    assert updated is not None
    assert updated.name == "renamed"
    await harness.send(
        "CHANNEL_PINS_UPDATE", {"channel_id": "40", "last_pin_timestamp": "2024-02-02T00:00:00+00:00"}
    )
    pinned = await harness.store.get_channel(40)
    assert pinned is not None
    assert pinned.last_pin_timestamp is not None
    await harness.send("CHANNEL_DELETE", channel(40))
    assert await harness.store.get_channel(40) is None


async def test_obfuscated_channels_are_cached_as_sent() -> None:
    harness = await Harness().started()
    await harness.send("CHANNEL_UPDATE", channel(40) | {"name": "___hidden___", "flags": 1 << 17})
    cached = await harness.store.get_channel(40)
    assert cached is not None
    assert cached.is_obfuscated
    assert cached.visible_name is None


async def test_role_and_emoji_events() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_ROLE_CREATE", {"guild_id": str(GUILD_ID), "role": role(21)})
    assert await harness.store.get_role(21) is not None
    await harness.send("GUILD_ROLE_DELETE", {"guild_id": str(GUILD_ID), "role_id": "21"})
    assert await harness.store.get_role(21) is None
    await harness.send(
        "GUILD_EMOJIS_UPDATE", {"guild_id": str(GUILD_ID), "emojis": [{"id": "31", "name": "f"}]}
    )
    assert await harness.store.get_emoji(30) is None
    assert await harness.store.get_emoji(31) is not None


async def test_member_events() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_MEMBER_ADD", member(3) | {"guild_id": str(GUILD_ID)})
    assert await harness.store.get_member(GUILD_ID, 3) is not None
    update = {"guild_id": str(GUILD_ID), "roles": ["20"], "user": user(3), "avatar": None, "banner": None}
    await harness.send("GUILD_MEMBER_UPDATE", update | {"joined_at": None, "nick": "new"})
    updated = await harness.store.get_member(GUILD_ID, 3)
    assert updated is not None
    assert updated.nick == "new"
    assert updated.roles == [Snowflake(20)]
    await harness.send("GUILD_MEMBER_UPDATE", update | {"joined_at": None})
    kept = await harness.store.get_member(GUILD_ID, 3)
    assert kept is not None
    assert kept.nick == "new"
    await harness.send("GUILD_MEMBER_REMOVE", {"guild_id": str(GUILD_ID), "user": user(2)})
    assert await harness.store.get_member(GUILD_ID, 2) is None
    assert await harness.store.get_presence(GUILD_ID, 2) is None
    assert await harness.store.get_voice_state(GUILD_ID, 2) is None


async def test_member_update_for_an_uncached_member_is_cached() -> None:
    harness = await Harness().started()
    update: Json = {
        "guild_id": str(GUILD_ID),
        "roles": [],
        "user": user(9),
        "avatar": None,
        "banner": None,
        "joined_at": None,
    }
    await harness.send("GUILD_MEMBER_UPDATE", update)
    cached = await harness.store.get_member(GUILD_ID, 9)
    assert cached is not None
    assert not cached.deaf


async def test_member_chunks_include_presences() -> None:
    harness = await Harness().started()
    chunk = {
        "guild_id": str(GUILD_ID),
        "members": [member(5)],
        "chunk_index": 0,
        "chunk_count": 1,
        "presences": [presence(5, "idle")],
    }
    await harness.send("GUILD_MEMBERS_CHUNK", chunk)
    assert await harness.store.get_member(GUILD_ID, 5) is not None
    cached = await harness.store.get_presence(GUILD_ID, 5)
    assert cached is not None
    assert cached.status == "idle"


async def test_message_events() -> None:
    harness = await Harness().started()
    await harness.send("MESSAGE_CREATE", message(100))
    await harness.send("MESSAGE_UPDATE", message(100, content="edited"))
    edited = await harness.store.get_message(100)
    assert edited is not None
    assert edited.content == "edited"
    await harness.send("MESSAGE_CREATE", message(101))
    await harness.send("MESSAGE_DELETE_BULK", {"ids": ["100", "101"], "channel_id": "40"})
    assert await harness.store.get_message(100) is None
    await harness.send("MESSAGE_CREATE", message(102))
    await harness.send("MESSAGE_DELETE", {"id": "102", "channel_id": "40"})
    assert await harness.store.get_message(102) is None


async def test_reactions_count_and_track_our_own() -> None:
    harness = await Harness().started()
    await harness.send("MESSAGE_CREATE", message(100))
    fire = {"id": None, "name": "🔥"}
    base = {"channel_id": "40", "message_id": "100", "emoji": fire, "burst": False, "type": 0}
    await harness.send("MESSAGE_REACTION_ADD", base | {"user_id": str(SELF_ID)})
    await harness.send("MESSAGE_REACTION_ADD", base | {"user_id": "2"})
    await harness.send("MESSAGE_REACTION_ADD", base | {"user_id": "3", "burst": True, "type": 1})
    cached = await harness.store.get_message(100)
    assert cached is not None
    assert isinstance(cached.reactions, list)
    [reaction] = cached.reactions
    assert reaction.count == 3
    assert (reaction.count_details.normal, reaction.count_details.burst) == (2, 1)
    assert reaction.me
    assert not reaction.me_burst

    await harness.send("MESSAGE_REACTION_REMOVE", base | {"user_id": str(SELF_ID)})
    cached = await harness.store.get_message(100)
    assert cached is not None
    assert isinstance(cached.reactions, list)
    assert cached.reactions[0].count == 2
    assert not cached.reactions[0].me

    custom = {"id": "77", "name": "custom"}
    await harness.send("MESSAGE_REACTION_ADD", base | {"user_id": "2", "emoji": custom})
    await harness.send(
        "MESSAGE_REACTION_REMOVE_EMOJI", {"channel_id": "40", "message_id": "100", "emoji": fire}
    )
    cached = await harness.store.get_message(100)
    assert cached is not None
    assert isinstance(cached.reactions, list)
    assert [reaction.emoji.id for reaction in cached.reactions] == [Snowflake(77)]
    await harness.send("MESSAGE_REACTION_REMOVE", base | {"user_id": "2", "emoji": custom})
    cached = await harness.store.get_message(100)
    assert cached is not None
    assert cached.reactions == []

    await harness.send("MESSAGE_REACTION_ADD", base | {"user_id": "2"})
    await harness.send("MESSAGE_REACTION_REMOVE_ALL", {"channel_id": "40", "message_id": "100"})
    cached = await harness.store.get_message(100)
    assert cached is not None
    assert cached.reactions == []


async def test_reactions_on_uncached_messages_are_ignored() -> None:
    harness = await Harness().started()
    reaction = {"user_id": "2", "channel_id": "40", "message_id": "999", "emoji": {"id": None, "name": "x"}}
    await harness.send("MESSAGE_REACTION_ADD", reaction | {"burst": False, "type": 0})
    assert await harness.store.get_message(999) is None


async def test_thread_events() -> None:
    harness = await Harness().started()
    await harness.send("THREAD_CREATE", channel(50, kind=11, parent=40))
    await harness.send("THREAD_CREATE", channel(51, kind=11, parent=40))
    await harness.send("THREAD_MEMBERS_UPDATE", {"id": "50", "guild_id": str(GUILD_ID), "member_count": 7})
    thread = await harness.store.get_channel(50)
    assert thread is not None
    assert thread.member_count == 7
    sync = {
        "guild_id": str(GUILD_ID),
        "channel_ids": ["40"],
        "threads": [channel(50, kind=11, parent=40)],
        "members": [],
    }
    await harness.send("THREAD_CREATE", channel(52, kind=11, parent=45))
    await harness.send("THREAD_LIST_SYNC", sync)
    assert await harness.store.get_channel(50) is not None
    assert await harness.store.get_channel(51) is None
    assert await harness.store.get_channel(52) is not None
    await harness.send("THREAD_DELETE", {"id": "50", "type": 11, "guild_id": str(GUILD_ID)})
    assert await harness.store.get_channel(50) is None


async def test_voice_presence_and_user_events() -> None:
    harness = await Harness().started()
    await harness.send(
        "VOICE_STATE_UPDATE", voice_state(3, 40) | {"guild_id": str(GUILD_ID), "member": member(3)}
    )
    assert await harness.store.get_voice_state(GUILD_ID, 3) is not None
    assert await harness.store.get_member(GUILD_ID, 3) is not None
    await harness.send("VOICE_STATE_UPDATE", voice_state(3, None) | {"guild_id": str(GUILD_ID)})
    assert await harness.store.get_voice_state(GUILD_ID, 3) is None
    await harness.send("PRESENCE_UPDATE", presence(2, "dnd") | {"guild_id": str(GUILD_ID)})
    cached = await harness.store.get_presence(GUILD_ID, 2)
    assert cached is not None
    assert cached.status == "dnd"
    await harness.send("USER_UPDATE", user(SELF_ID, "renamed"))
    me = await harness.store.get_user(SELF_ID)
    assert me is not None
    assert me.username == "renamed"


async def test_resumed_confirms_a_snapshot_that_lines_up(tmp_path: Path) -> None:
    harness = Harness()
    await harness.send("READY", ready(), sequence=1)
    await harness.send("GUILD_CREATE", guild_create(), sequence=2)
    path = tmp_path / "snapshot"
    await harness.store.save_snapshot(path)
    restarted = Harness()
    await restarted.store.load_snapshot(path)
    assert await restarted.store.get_user(2, fresh_only=True) is None
    await restarted.send("RESUMED", None, sequence=3)
    assert await restarted.store.get_user(2, fresh_only=True) is not None


async def test_unhandled_events_are_ignored() -> None:
    harness = Harness()
    await harness.send("TYPING_START", {"anything": True})
    assert harness.store.revision == 0


async def test_one_shard_reconnecting_does_not_stale_another() -> None:
    harness = await Harness().started()
    await harness.send("READY", ready(), shard=1)
    assert await harness.store.get_channel(40, fresh_only=True) is not None


async def test_guild_create_fields_survive_updates_and_follow_member_counts() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_UPDATE", {k: v for k, v in guild_create(name="renamed").items() if k not in {
        "joined_at", "large", "member_count", "members", "channels", "threads", "voice_states", "presences"
    }})  # fmt: skip
    guild = await harness.store.get_guild(GUILD_ID)
    assert guild is not None
    assert guild.name == "renamed"
    assert guild.large is False
    assert guild.member_count == 1
    await harness.send("GUILD_MEMBER_ADD", member(3) | {"guild_id": str(GUILD_ID)})
    await harness.send("GUILD_MEMBER_ADD", member(4) | {"guild_id": str(GUILD_ID)})
    await harness.send("GUILD_MEMBER_REMOVE", {"guild_id": str(GUILD_ID), "user": user(3)})
    counted = await harness.store.get_guild(GUILD_ID)
    assert counted is not None
    assert counted.member_count == 2


async def test_a_guild_outage_then_guild_create_drops_what_was_deleted_meanwhile() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_DELETE", {"id": str(GUILD_ID), "unavailable": True})
    await harness.send("GUILD_CREATE", guild_create(channels=[channel(41)]))
    assert await harness.store.get_channel(40) is None
    assert await harness.store.get_channel(41) is not None


async def test_guilds_unavailable_at_startup_survive_the_sweep(tmp_path: Path) -> None:
    harness = await Harness().started()
    path = tmp_path / "snapshot"
    await harness.store.save_snapshot(path)
    restarted = Harness()
    await restarted.store.load_snapshot(path)
    await restarted.send("READY", ready())
    await restarted.store.sweep_stale()
    assert await restarted.store.get_channel(40) is not None
    await restarted.send("GUILD_CREATE", guild_create())
    assert await restarted.store.get_channel(40, fresh_only=True) is not None


async def test_deleting_a_role_removes_it_from_members() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_MEMBER_ADD", member(3) | {"guild_id": str(GUILD_ID), "roles": ["20"]})
    await harness.send("GUILD_ROLE_DELETE", {"guild_id": str(GUILD_ID), "role_id": "20"})
    cached = await harness.store.get_member(GUILD_ID, 3)
    assert cached is not None
    assert cached.roles == []


async def test_deleting_a_channel_removes_its_threads_and_messages() -> None:
    harness = await Harness().started()
    await harness.send("THREAD_CREATE", channel(50, kind=11, parent=40))
    await harness.send("MESSAGE_CREATE", message(100))
    await harness.send("CHANNEL_DELETE", channel(40))
    assert await harness.store.get_channel(50) is None
    assert await harness.store.get_message(100) is None


async def test_a_reaction_does_not_make_a_stale_message_fresh() -> None:
    harness = await Harness().started()
    await harness.send("MESSAGE_CREATE", message(100))
    await harness.send("READY", ready())
    reaction = {"user_id": "2", "channel_id": "40", "message_id": "100", "emoji": {"id": None, "name": "x"}}
    await harness.send("MESSAGE_REACTION_ADD", reaction | {"burst": False, "type": 0})
    assert await harness.store.get_message(100, fresh_only=True) is None
    cached = await harness.store.get_message(100)
    assert cached is not None
    assert isinstance(cached.reactions, list)
    assert cached.reactions[0].count == 1


async def test_members_are_kept_when_guild_create_cannot_list_them_all() -> None:
    harness = Harness(Intents(guilds=True))
    await harness.started()
    await harness.send("GUILD_MEMBER_ADD", member(3) | {"guild_id": str(GUILD_ID)})
    await harness.send("READY", ready())
    await harness.send("GUILD_CREATE", guild_create(members=[], presences=[]))
    assert await harness.store.get_member(GUILD_ID, 3) is not None
    assert await harness.store.get_presence(GUILD_ID, 2) is not None


async def test_a_member_update_does_not_confirm_a_stale_member(tmp_path: Path) -> None:
    harness = await Harness().started()
    path = tmp_path / "snapshot"
    await harness.store.save_snapshot(path)
    restarted = Harness()
    await restarted.store.load_snapshot(path)
    update: Json = {"guild_id": str(GUILD_ID), "roles": [], "user": user(2), "avatar": None, "banner": None}
    await restarted.send("GUILD_MEMBER_UPDATE", update | {"joined_at": None, "nick": "renamed"})
    cached = await restarted.store.get_member(GUILD_ID, 2)
    assert cached is not None
    assert cached.nick == "renamed"
    assert await restarted.store.get_member(GUILD_ID, 2, fresh_only=True) is None


async def test_archived_threads_leave_the_cache() -> None:
    harness = await Harness().started()
    await harness.send("THREAD_CREATE", channel(50, kind=11, parent=40))
    metadata = {
        "archived": True,
        "auto_archive_duration": 60,
        "archive_timestamp": "2024-01-01T00:00:00+00:00",
        "locked": False,
    }
    await harness.send("THREAD_UPDATE", channel(50, kind=11, parent=40) | {"thread_metadata": metadata})
    assert await harness.store.get_channel(50) is None


def sticker(sticker_id: int) -> Json:
    return {
        "id": str(sticker_id),
        "name": "party",
        "description": None,
        "tags": "tada",
        "type": 2,
        "format_type": 1,
        "available": True,
        "guild_id": str(GUILD_ID),
    }


def scheduled_event(event_id: int, *, user_count: int | None = 3) -> Json:
    event: Json = {
        "id": str(event_id),
        "guild_id": str(GUILD_ID),
        "channel_id": None,
        "creator_id": "1",
        "name": "Meetup",
        "description": None,
        "scheduled_start_time": "2026-02-01T18:00:00+00:00",
        "scheduled_end_time": "2026-02-01T20:00:00+00:00",
        "privacy_level": 2,
        "status": 1,
        "entity_type": 3,
        "entity_id": None,
        "entity_metadata": {"location": "Town hall"},
        "image": None,
        "recurrence_rule": None,
    }
    if user_count is not None:
        event["user_count"] = user_count
    return event


def stage(stage_id: int, topic: str = "Live") -> Json:
    return {
        "id": str(stage_id),
        "guild_id": str(GUILD_ID),
        "channel_id": "40",
        "topic": topic,
        "privacy_level": 2,
        "discoverable_disabled": False,
        "guild_scheduled_event_id": None,
    }


def sound(sound_id: int, name: str = "quack", *, with_guild: bool = True) -> Json:
    data: Json = {
        "name": name,
        "sound_id": str(sound_id),
        "volume": 1.0,
        "emoji_id": None,
        "emoji_name": None,
        "available": True,
    }
    if with_guild:
        data["guild_id"] = str(GUILD_ID)
    return data


async def test_guild_create_caches_stickers_stages_events_and_sounds() -> None:
    harness = Harness()
    await harness.send("READY", ready())
    await harness.send(
        "GUILD_CREATE",
        guild_create(
            stickers=[sticker(70)],
            stage_instances=[stage(71)],
            guild_scheduled_events=[scheduled_event(72)],
            soundboard_sounds=[sound(73, with_guild=False)],
        ),
    )
    store = harness.store
    assert (await store.get_sticker(70)) is not None
    assert (await store.get_stage_instance(71)) is not None
    assert (await store.get_scheduled_event(72)) is not None
    cached_sound = await store.get_soundboard_sound(73)
    assert cached_sound is not None
    assert cached_sound.guild_id == GUILD_ID  # filled in: GUILD_CREATE leaves it out
    guild = await store.get_guild(GUILD_ID)
    assert guild is not None
    assert guild.stickers == []  # stickers live in their own collection


async def test_a_second_guild_create_drops_what_the_guild_no_longer_has() -> None:
    harness = Harness()
    await harness.send("READY", ready())
    await harness.send(
        "GUILD_CREATE",
        guild_create(stickers=[sticker(70)], stage_instances=[stage(71)], soundboard_sounds=[sound(73)]),
    )
    await harness.send("GUILD_CREATE", guild_create(stickers=[]))
    assert await harness.store.get_sticker(70) is None
    assert await harness.store.get_stage_instance(71) is None
    assert await harness.store.get_soundboard_sound(73) is None


async def test_a_guild_create_without_a_sticker_list_keeps_the_stickers() -> None:
    harness = Harness()
    await harness.send("READY", ready())
    await harness.send("GUILD_CREATE", guild_create(stickers=[sticker(70)]))
    await harness.send("GUILD_CREATE", guild_create())
    assert await harness.store.get_sticker(70) is not None


async def test_stickers_update_replaces_the_guilds_stickers() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_STICKERS_UPDATE", {"guild_id": str(GUILD_ID), "stickers": [sticker(70)]})
    await harness.send("GUILD_STICKERS_UPDATE", {"guild_id": str(GUILD_ID), "stickers": [sticker(71)]})
    assert await harness.store.get_sticker(70) is None
    assert await harness.store.get_sticker(71) is not None


async def test_scheduled_events_follow_their_events_and_subscriber_counts() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_SCHEDULED_EVENT_CREATE", scheduled_event(72))
    subscription = {"guild_scheduled_event_id": "72", "user_id": "2", "guild_id": str(GUILD_ID)}
    await harness.send("GUILD_SCHEDULED_EVENT_USER_ADD", subscription)
    await harness.send("GUILD_SCHEDULED_EVENT_USER_ADD", subscription | {"user_id": "3"})
    await harness.send("GUILD_SCHEDULED_EVENT_USER_REMOVE", subscription)
    cached = await harness.store.get_scheduled_event(72)
    assert cached is not None
    assert cached.user_count == 4
    await harness.send("GUILD_SCHEDULED_EVENT_UPDATE", scheduled_event(72) | {"name": "Moved"})
    cached = await harness.store.get_scheduled_event(72)
    assert cached is not None
    assert cached.name == "Moved"
    await harness.send("GUILD_SCHEDULED_EVENT_DELETE", scheduled_event(72))
    assert await harness.store.get_scheduled_event(72) is None


async def test_an_unknown_subscriber_count_stays_unknown() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_SCHEDULED_EVENT_CREATE", scheduled_event(72, user_count=None))
    subscription = {"guild_scheduled_event_id": "72", "user_id": "2", "guild_id": str(GUILD_ID)}
    await harness.send("GUILD_SCHEDULED_EVENT_USER_ADD", subscription)
    cached = await harness.store.get_scheduled_event(72)
    assert cached is not None
    assert cached.user_count is msgspec.UNSET


async def test_stage_instances_follow_their_events() -> None:
    harness = await Harness().started()
    await harness.send("STAGE_INSTANCE_CREATE", stage(71))
    await harness.send("STAGE_INSTANCE_UPDATE", stage(71, "Q&A"))
    cached = await harness.store.get_stage_instance(71)
    assert cached is not None
    assert cached.topic == "Q&A"
    await harness.send("STAGE_INSTANCE_DELETE", stage(71))
    assert await harness.store.get_stage_instance(71) is None


async def test_soundboard_sounds_follow_their_events() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_SOUNDBOARD_SOUND_CREATE", sound(73))
    await harness.send("GUILD_SOUNDBOARD_SOUND_UPDATE", sound(73, "honk"))
    cached = await harness.store.get_soundboard_sound(73)
    assert cached is not None
    assert cached.name == "honk"
    await harness.send(
        "GUILD_SOUNDBOARD_SOUNDS_UPDATE", {"guild_id": str(GUILD_ID), "soundboard_sounds": [sound(74)]}
    )
    assert await harness.store.get_soundboard_sound(73) is not None  # a partial update keeps the others
    await harness.send("GUILD_SOUNDBOARD_SOUND_DELETE", {"sound_id": "73", "guild_id": str(GUILD_ID)})
    assert await harness.store.get_soundboard_sound(73) is None
    assert await harness.store.get_soundboard_sound(74) is not None


async def test_requested_soundboard_sounds_replace_the_guilds_list() -> None:
    harness = await Harness().started()
    await harness.send("GUILD_SOUNDBOARD_SOUND_CREATE", sound(73))
    listed = {"guild_id": str(GUILD_ID), "soundboard_sounds": [sound(75, with_guild=False)]}
    await harness.send("SOUNDBOARD_SOUNDS", listed)
    assert await harness.store.get_soundboard_sound(73) is None
    cached = await harness.store.get_soundboard_sound(75)
    assert cached is not None
    assert cached.guild_id == GUILD_ID


def poll_message(message_id: int, counts: list[Json] | None) -> Json:
    poll: Json = {
        "question": {"text": "Lunch?"},
        "answers": [{"answer_id": 1, "poll_media": {"text": "Pizza"}}],
        "expiry": "2026-01-02T00:00:00+00:00",
        "allow_multiselect": False,
        "layout_type": 1,
    }
    if counts is not None:
        poll["results"] = {"is_finalized": False, "answer_counts": counts}
    return message(message_id, poll=poll)


async def test_poll_votes_update_the_cached_counts() -> None:
    harness = await Harness().started()
    await harness.send("MESSAGE_CREATE", poll_message(50, [{"id": 1, "count": 1, "me_voted": False}]))
    vote = {"user_id": str(SELF_ID), "channel_id": "40", "message_id": "50", "guild_id": str(GUILD_ID)}
    await harness.send("MESSAGE_POLL_VOTE_ADD", vote | {"answer_id": 1})
    await harness.send("MESSAGE_POLL_VOTE_ADD", vote | {"user_id": "2", "answer_id": 2})
    cached = await harness.store.get_message(50)
    assert cached is not None
    assert not isinstance(cached.poll, msgspec.UnsetType)
    assert not isinstance(cached.poll.results, msgspec.UnsetType)
    counts = {count.id: (count.count, count.me_voted) for count in cached.poll.results.answer_counts}
    assert counts == {1: (2, True), 2: (1, False)}
    await harness.send("MESSAGE_POLL_VOTE_REMOVE", vote | {"answer_id": 1})
    await harness.send("MESSAGE_POLL_VOTE_REMOVE", vote | {"user_id": "2", "answer_id": 2})
    cached = await harness.store.get_message(50)
    assert cached is not None
    assert not isinstance(cached.poll, msgspec.UnsetType)
    assert not isinstance(cached.poll.results, msgspec.UnsetType)
    assert [(count.id, count.count, count.me_voted) for count in cached.poll.results.answer_counts] == [
        (1, 1, False)
    ]


async def test_poll_votes_without_known_results_change_nothing() -> None:
    harness = await Harness().started()
    await harness.send("MESSAGE_CREATE", poll_message(50, None))
    vote = {"user_id": "2", "channel_id": "40", "message_id": "50", "guild_id": str(GUILD_ID), "answer_id": 1}
    await harness.send("MESSAGE_POLL_VOTE_ADD", vote)
    cached = await harness.store.get_message(50)
    assert cached is not None
    assert not isinstance(cached.poll, msgspec.UnsetType)
    assert cached.poll.results is msgspec.UNSET


def thread_member(thread_id: int, user_id: int, **extra: object) -> Json:
    return {
        "id": str(thread_id),
        "user_id": str(user_id),
        "join_timestamp": "2024-01-01T00:00:00+00:00",
        "flags": 0,
    } | extra


async def test_thread_membership_of_the_bot_is_tracked() -> None:
    harness = await Harness().started()
    await harness.send("THREAD_CREATE", channel(60, kind=11, parent=40))
    await harness.send("THREAD_MEMBER_UPDATE", thread_member(60, SELF_ID, guild_id=str(GUILD_ID)))
    thread = await harness.store.get_channel(60)
    assert thread is not None
    assert not isinstance(thread.member, msgspec.UnsetType)
    assert thread.member.user_id == SELF_ID
    removed = {"id": "60", "guild_id": str(GUILD_ID), "member_count": 1, "removed_member_ids": [str(SELF_ID)]}
    await harness.send("THREAD_MEMBERS_UPDATE", removed)
    thread = await harness.store.get_channel(60)
    assert thread is not None
    assert thread.member is msgspec.UNSET
    assert thread.member_count == 1


async def test_added_thread_members_bring_their_member_and_presence() -> None:
    harness = await Harness().started()
    await harness.send("THREAD_CREATE", channel(60, kind=11, parent=40))
    added = {
        "id": "60",
        "guild_id": str(GUILD_ID),
        "member_count": 2,
        "added_members": [
            thread_member(60, SELF_ID, member=member(SELF_ID), presence=None),
            thread_member(60, 5, member=member(5, nick="new"), presence=presence(5, "idle")),
        ],
    }
    await harness.send("THREAD_MEMBERS_UPDATE", added)
    thread = await harness.store.get_channel(60)
    assert thread is not None
    assert not isinstance(thread.member, msgspec.UnsetType)
    cached_member = await harness.store.get_member(GUILD_ID, 5)
    assert cached_member is not None
    assert cached_member.nick == "new"
    cached_presence = await harness.store.get_presence(GUILD_ID, 5)
    assert cached_presence is not None
    assert cached_presence.status == "idle"


async def test_forgetting_a_guild_forgets_its_newer_kinds() -> None:
    harness = Harness()
    await harness.send("READY", ready())
    await harness.send(
        "GUILD_CREATE",
        guild_create(
            stickers=[sticker(70)],
            stage_instances=[stage(71)],
            guild_scheduled_events=[scheduled_event(72)],
            soundboard_sounds=[sound(73)],
        ),
    )
    await harness.send("GUILD_DELETE", {"id": str(GUILD_ID)})
    store = harness.store
    assert await store.get_sticker(70) is None
    assert await store.get_stage_instance(71) is None
    assert await store.get_scheduled_event(72) is None
    assert await store.get_soundboard_sound(73) is None
