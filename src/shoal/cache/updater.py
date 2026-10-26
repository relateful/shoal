"""Applies gateway dispatches to a `CacheStore`.

The updater consumes `shoal.core.DispatchEvent`, so the same updater runs next to the shards or in a
worker process that receives events over `shoal.ipc`.

Every event that changes a cached kind is handled; `handled_events` lists them and the tests pin that
list, so an event cannot silently fall out. Events about things the cache does not hold (integrations,
invites, bans, Auto Moderation, entitlements, subscriptions, typing) pass through untouched.
"""

import logging
from collections.abc import Awaitable, Callable, Hashable
from typing import final

import msgspec
from msgspec import UNSET

from shoal.cache.collection import CacheCollection
from shoal.cache.entry import Source
from shoal.cache.guild import CachedGuild
from shoal.cache.store import CacheStore
from shoal.core.codec import PayloadDecodeError, decode_msgpack, encode_msgpack
from shoal.core.dispatch import DispatchEvent
from shoal.core.snowflake import Snowflake
from shoal.payloads.channel import Channel, ThreadMember
from shoal.payloads.emoji import Emoji
from shoal.payloads.gateway import Intents
from shoal.payloads.gateway_events import (
    GUILD_CREATE_MEMBER_LIMIT,
    ChannelPinsUpdate,
    GuildCreate,
    GuildDelete,
    GuildEmojisUpdate,
    GuildMemberAdd,
    GuildMemberRemove,
    GuildMembersChunk,
    GuildMemberUpdate,
    GuildRoleCreate,
    GuildRoleDelete,
    GuildScheduledEventUserAdd,
    GuildSoundboardSoundDelete,
    GuildSoundboardSoundsUpdate,
    GuildStickersUpdate,
    MessageDelete,
    MessageDeleteBulk,
    MessagePollVoteAdd,
    MessageReactionAdd,
    MessageReactionRemove,
    MessageReactionRemoveAll,
    MessageReactionRemoveEmoji,
    MessageUpdate,
    Presence,
    PresenceUpdate,
    Ready,
    SoundboardSounds,
    ThreadListSync,
    ThreadMembersUpdate,
    ThreadMemberUpdate,
)
from shoal.payloads.guild import Guild, GuildMember, GuildMemberFlags, UnavailableGuild
from shoal.payloads.message import Message, Reaction, ReactionCountDetails
from shoal.payloads.poll import PollAnswerCount
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.soundboard import SoundboardSound
from shoal.payloads.stage_instance import StageInstance
from shoal.payloads.user import User
from shoal.payloads.voice import VoiceState

_log = logging.getLogger("shoal.cache")

type _Handler = Callable[[DispatchEvent], Awaitable[None]]


def _same_emoji(left: Emoji, right: Emoji) -> bool:
    """Custom emoji match by ID, unicode emoji by name."""
    if left.id is not None or right.id is not None:
        return left.id == right.id
    return left.name == right.name


def _known[T](value: T | msgspec.UnsetType, fallback: T) -> T:
    """`value` unless Discord left it out, in which case the previously known `fallback`."""
    return fallback if isinstance(value, msgspec.UnsetType) else value


def _cached_guild(guild: Guild) -> CachedGuild:
    """`guild` without its roles, emojis and stickers (and a `GuildCreate`'s startup lists), as cached.

    Re-encoding keeps every field `CachedGuild` shares with the source, whichever type it is.
    """
    trimmed = msgspec.structs.replace(guild, roles=[], emojis=[], stickers=[])
    return decode_msgpack(encode_msgpack(trimmed), CachedGuild)


def _membership(member: ThreadMember) -> ThreadMember:
    """The bot's thread membership as a thread holds it, without an event's extra fields."""
    return ThreadMember(
        id=member.id, user_id=member.user_id, join_timestamp=member.join_timestamp, flags=member.flags
    )


_EMPTY_MEMBER = GuildMember(roles=[], joined_at=None, deaf=False, mute=False, flags=GuildMemberFlags())
"""What `GUILD_MEMBER_UPDATE` merges into when the member was not cached. Optional fields Discord omits
stay unset. `deaf`, `mute` and `flags` have no "unknown" value in `GuildMember`, so until a full member
object arrives (`GUILD_MEMBER_ADD`, a member chunk or a REST fetch) they read as false and empty."""


@final
class CacheUpdater:
    """Keeps a `CacheStore` in sync with gateway dispatches.

    Call `apply` for every dispatch, in order per shard. On `READY` the store starts a new session for
    that shard; on `RESUMED` it confirms the shard's restored snapshot if it lines up with the replay.
    After each `GUILD_CREATE` the guild is reconciled, which removes channels, roles, voice states and
    (when the event listed them all) members and presences that disappeared while the bot was offline
    or the guild was unavailable.

    Args:
        store: The store to keep in sync.
        intents: The intents the shards identify with. `GUILD_CREATE` lists every member only with
            `guild_presences` in a guild that is not large, and every non-offline presence only
            with `guild_presences` in a guild of at most 75,000 members. Without `intents` the
            updater never assumes a complete list, so members and presences are never reconciled
            away.
    """

    __slots__ = ("_handlers", "_intents", "_self_id", "_store")

    def __init__(self, store: CacheStore, *, intents: Intents | None = None) -> None:
        """Bind the updater to a store; see the class docstring for the arguments."""
        self._store: CacheStore = store
        self._intents: Intents | None = intents
        self._self_id: Snowflake | None = None
        self._handlers: dict[str, _Handler] = {
            "CHANNEL_CREATE": self._channel_upsert,
            "CHANNEL_DELETE": self._channel_delete,
            "CHANNEL_PINS_UPDATE": self._channel_pins_update,
            "CHANNEL_UPDATE": self._channel_upsert,
            "GUILD_CREATE": self._guild_create,
            "GUILD_DELETE": self._guild_delete,
            "GUILD_EMOJIS_UPDATE": self._guild_emojis_update,
            "GUILD_MEMBERS_CHUNK": self._guild_members_chunk,
            "GUILD_MEMBER_ADD": self._guild_member_add,
            "GUILD_MEMBER_REMOVE": self._guild_member_remove,
            "GUILD_MEMBER_UPDATE": self._guild_member_update,
            "GUILD_ROLE_CREATE": self._guild_role_upsert,
            "GUILD_ROLE_DELETE": self._guild_role_delete,
            "GUILD_ROLE_UPDATE": self._guild_role_upsert,
            "GUILD_SCHEDULED_EVENT_CREATE": self._scheduled_event_upsert,
            "GUILD_SCHEDULED_EVENT_DELETE": self._scheduled_event_delete,
            "GUILD_SCHEDULED_EVENT_UPDATE": self._scheduled_event_upsert,
            "GUILD_SCHEDULED_EVENT_USER_ADD": self._scheduled_event_user_add,
            "GUILD_SCHEDULED_EVENT_USER_REMOVE": self._scheduled_event_user_remove,
            "GUILD_SOUNDBOARD_SOUNDS_UPDATE": self._soundboard_sounds_update,
            "GUILD_SOUNDBOARD_SOUND_CREATE": self._soundboard_sound_upsert,
            "GUILD_SOUNDBOARD_SOUND_DELETE": self._soundboard_sound_delete,
            "GUILD_SOUNDBOARD_SOUND_UPDATE": self._soundboard_sound_upsert,
            "GUILD_STICKERS_UPDATE": self._guild_stickers_update,
            "GUILD_UPDATE": self._guild_update,
            "MESSAGE_CREATE": self._message_upsert,
            "MESSAGE_DELETE": self._message_delete,
            "MESSAGE_DELETE_BULK": self._message_delete_bulk,
            "MESSAGE_POLL_VOTE_ADD": self._poll_vote_add,
            "MESSAGE_POLL_VOTE_REMOVE": self._poll_vote_remove,
            "MESSAGE_REACTION_ADD": self._message_reaction_add,
            "MESSAGE_REACTION_REMOVE": self._message_reaction_remove,
            "MESSAGE_REACTION_REMOVE_ALL": self._message_reaction_remove_all,
            "MESSAGE_REACTION_REMOVE_EMOJI": self._message_reaction_remove_emoji,
            "MESSAGE_UPDATE": self._message_upsert,
            "PRESENCE_UPDATE": self._presence_update,
            "READY": self._ready,
            "RESUMED": self._resumed,
            "SOUNDBOARD_SOUNDS": self._soundboard_sounds,
            "STAGE_INSTANCE_CREATE": self._stage_instance_upsert,
            "STAGE_INSTANCE_DELETE": self._stage_instance_delete,
            "STAGE_INSTANCE_UPDATE": self._stage_instance_upsert,
            "THREAD_CREATE": self._channel_upsert,
            "THREAD_DELETE": self._channel_delete,
            "THREAD_LIST_SYNC": self._thread_list_sync,
            "THREAD_MEMBERS_UPDATE": self._thread_members_update,
            "THREAD_MEMBER_UPDATE": self._thread_member_update,
            "THREAD_UPDATE": self._channel_upsert,
            "USER_UPDATE": self._user_update,
            "VOICE_STATE_UPDATE": self._voice_state_update,
        }

    @property
    def handled_events(self) -> frozenset[str]:
        """The dispatch names this updater applies."""
        return frozenset(self._handlers)

    async def apply(self, event: DispatchEvent) -> None:
        """Apply one dispatch. Undecodable data is logged and skipped, never raised.

        Has the `DispatchHandler` signature, so it can be a shard's `dispatch` directly. Events of
        different shards may be applied concurrently; each shard's must arrive in order.
        """
        if event.sequence is not None:
            self._store.observe(event.shard_id, event.sequence)
        handler = self._handlers.get(event.name)
        if handler is None:
            return
        try:
            await handler(event)
        except PayloadDecodeError:
            _log.exception("cache could not decode %s; the event was not applied", event.name)

    async def _put[K: Hashable, V](
        self,
        event: DispatchEvent,
        collection: CacheCollection[K, V],
        key: K,
        value: V,
        scope: Snowflake | None,
    ) -> None:
        await self._store.put(collection, key, value, Source.GATEWAY, scope=scope, shard=event.shard_id)

    async def _channel_delete(self, event: DispatchEvent) -> None:
        channel = event.decode(Channel)
        scope = channel.guild_id if isinstance(channel.guild_id, Snowflake) else None
        await self._store.channels.delete(channel.id)
        gone = {channel.id}
        for thread_id, thread in await self._store.channels.scoped(scope):
            if thread.value.parent_id == channel.id and thread.value.type.is_thread:
                await self._store.channels.delete(thread_id)
                gone.add(thread_id)
        for message_id, message in await self._store.messages.scoped(scope):
            if message.value.channel_id in gone:
                await self._store.messages.delete(message_id)

    async def _channel_pins_update(self, event: DispatchEvent) -> None:
        pins = event.decode(ChannelPinsUpdate)
        pinned = None if pins.last_pin_timestamp is UNSET else pins.last_pin_timestamp

        def update(channel: Channel) -> Channel:
            return msgspec.structs.replace(channel, last_pin_timestamp=pinned)

        await self._store.edit(self._store.channels, pins.channel_id, update)

    async def _channel_upsert(self, event: DispatchEvent) -> None:
        channel = event.decode(Channel)
        scope = channel.guild_id if isinstance(channel.guild_id, Snowflake) else None
        metadata = channel.thread_metadata
        if not isinstance(metadata, msgspec.UnsetType) and metadata.archived:
            # Only active threads are cached: nothing reports on archived ones, so they would
            # otherwise pile up for the whole session.
            await self._store.channels.delete(channel.id)
            return
        await self._put(event, self._store.channels, channel.id, channel, scope)

    async def _guild_create(self, event: DispatchEvent) -> None:
        status = event.decode(UnavailableGuild)
        if status.unavailable is True:
            _log.info("guild %s is unavailable (outage); keeping cached data", status.id)
            self._store.mark_unavailable(status.id)
            return
        guild = event.decode(GuildCreate)
        since = self._store.revision
        self._store.mark_available(guild.id)
        await self._store_guild(event, guild, _cached_guild(guild))
        for channel in (*guild.channels, *guild.threads):
            await self._put(event, self._store.channels, channel.id, channel, guild.id)
        for member in guild.members:
            await self._store_member(event, guild.id, member)
        for voice_state in guild.voice_states:
            await self._store_voice_state(event, guild.id, voice_state)
        for presence in guild.presences:
            await self._put(event, self._store.presences, (guild.id, presence.user.id), presence, guild.id)
        for stage in guild.stage_instances:
            await self._put(event, self._store.stage_instances, stage.id, stage, guild.id)
        for scheduled in guild.guild_scheduled_events:
            await self._put(event, self._store.scheduled_events, scheduled.id, scheduled, guild.id)
        for sound in guild.soundboard_sounds:
            await self._store_sound(event, guild.id, sound)
        presences_listed = self._intents is not None and self._intents.guild_presences
        removed = await self._store.reconcile_guild(
            guild.id,
            since=since,
            members=presences_listed and not guild.large,
            presences=presences_listed and guild.member_count <= GUILD_CREATE_MEMBER_LIMIT,
            stickers=not isinstance(guild.stickers, msgspec.UnsetType),
        )
        if removed:
            _log.debug("guild %s: dropped %d entries that no longer exist", guild.id, removed)

    async def _guild_delete(self, event: DispatchEvent) -> None:
        deleted = event.decode(GuildDelete)
        if deleted.unavailable is True:
            _log.info("guild %s became unavailable; keeping cached data", deleted.id)
            self._store.mark_unavailable(deleted.id)
            return
        await self._store.forget_guild(deleted.id)

    async def _guild_emojis_update(self, event: DispatchEvent) -> None:
        update = event.decode(GuildEmojisUpdate)
        current = {emoji.id: emoji for emoji in update.emojis if emoji.id is not None}
        await self._replace_scope(event, self._store.emojis, update.guild_id, current)

    async def _guild_stickers_update(self, event: DispatchEvent) -> None:
        update = event.decode(GuildStickersUpdate)
        current = {sticker.id: sticker for sticker in update.stickers}
        await self._replace_scope(event, self._store.stickers, update.guild_id, current)

    async def _guild_member_add(self, event: DispatchEvent) -> None:
        added = event.decode(GuildMemberAdd)
        await self._store_member(event, added.guild_id, added)
        await self._count_members(added.guild_id, 1)

    async def _guild_member_remove(self, event: DispatchEvent) -> None:
        removed = event.decode(GuildMemberRemove)
        key = (removed.guild_id, removed.user.id)
        await self._store.members.delete(key)
        await self._store.presences.delete(key)
        await self._store.voice_states.delete(key)
        await self._count_members(removed.guild_id, -1)

    async def _guild_member_update(self, event: DispatchEvent) -> None:
        update = event.decode(GuildMemberUpdate)
        entry = await self._store.members.get((update.guild_id, update.user.id))
        previous = entry.value if entry is not None else _EMPTY_MEMBER
        member = GuildMember(
            user=update.user,
            nick=_known(update.nick, previous.nick),
            avatar=update.avatar,
            banner=update.banner,
            roles=update.roles,
            joined_at=update.joined_at,
            premium_since=_known(update.premium_since, previous.premium_since),
            deaf=_known(update.deaf, previous.deaf),
            mute=_known(update.mute, previous.mute),
            flags=_known(update.flags, previous.flags),
            pending=_known(update.pending, previous.pending),
            communication_disabled_until=_known(
                update.communication_disabled_until, previous.communication_disabled_until
            ),
            avatar_decoration_data=_known(update.avatar_decoration_data, previous.avatar_decoration_data),
            collectibles=_known(update.collectibles, previous.collectibles),
        )
        if entry is not None and not self._store.is_fresh(entry):
            # Fields Discord left out came from an unconfirmed entry, so the result stays unconfirmed.
            await self._put(event, self._store.users, update.user.id, update.user, None)
            await self._store.edit(self._store.members, (update.guild_id, update.user.id), lambda _: member)
            return
        await self._store_member(event, update.guild_id, member)

    async def _guild_members_chunk(self, event: DispatchEvent) -> None:
        chunk = event.decode(GuildMembersChunk)
        for member in chunk.members:
            await self._store_member(event, chunk.guild_id, member)
        if chunk.presences is not UNSET:
            for presence in chunk.presences:
                key = (chunk.guild_id, presence.user.id)
                await self._put(event, self._store.presences, key, presence, chunk.guild_id)

    async def _guild_role_delete(self, event: DispatchEvent) -> None:
        deleted = event.decode(GuildRoleDelete)
        await self._store.roles.delete(deleted.role_id)

        def without_role(member: GuildMember) -> GuildMember:
            return msgspec.structs.replace(
                member, roles=[role for role in member.roles if role != deleted.role_id]
            )

        for key, entry in await self._store.members.scoped(deleted.guild_id):
            if deleted.role_id in entry.value.roles:
                await self._store.edit(self._store.members, key, without_role)

    async def _guild_role_upsert(self, event: DispatchEvent) -> None:
        upsert = event.decode(GuildRoleCreate)
        await self._put(event, self._store.roles, upsert.role.id, upsert.role, upsert.guild_id)

    async def _guild_update(self, event: DispatchEvent) -> None:
        guild = event.decode(Guild)
        cached = _cached_guild(guild)
        entry = await self._store.guilds.get(guild.id)
        if entry is None:
            await self._store_guild(event, guild, cached)
            return
        previous = entry.value
        merged = msgspec.structs.replace(
            cached,
            joined_at=_known(cached.joined_at, previous.joined_at),
            large=_known(cached.large, previous.large),
            member_count=_known(cached.member_count, previous.member_count),
        )
        if self._store.is_fresh(entry):
            await self._store_guild(event, guild, merged)
            return
        # `member_count` and friends came from an unconfirmed entry; the guild stays unconfirmed
        # until its next `GUILD_CREATE`. Its roles and emojis are complete in the event.
        await self._store_guild_contents(event, guild)
        await self._store.edit(self._store.guilds, guild.id, lambda _: merged)

    async def _message_delete(self, event: DispatchEvent) -> None:
        await self._store.messages.delete(event.decode(MessageDelete).id)

    async def _message_delete_bulk(self, event: DispatchEvent) -> None:
        for message_id in event.decode(MessageDeleteBulk).ids:
            await self._store.messages.delete(message_id)

    async def _message_reaction_add(self, event: DispatchEvent) -> None:
        added = event.decode(MessageReactionAdd)
        mine = added.user_id == self._self_id
        burst_colors = added.burst_colors if added.burst_colors is not UNSET else []

        def add(reactions: list[Reaction]) -> list[Reaction]:
            for index, reaction in enumerate(reactions):
                if _same_emoji(reaction.emoji, added.emoji):
                    details = reaction.count_details
                    reactions[index] = msgspec.structs.replace(
                        reaction,
                        count=reaction.count + 1,
                        count_details=ReactionCountDetails(
                            burst=details.burst + int(added.burst),
                            normal=details.normal + int(not added.burst),
                        ),
                        me=reaction.me or (mine and not added.burst),
                        me_burst=reaction.me_burst or (mine and added.burst),
                    )
                    return reactions
            details = ReactionCountDetails(burst=int(added.burst), normal=int(not added.burst))
            reaction = Reaction(
                count=1,
                count_details=details,
                me=mine and not added.burst,
                me_burst=mine and added.burst,
                emoji=added.emoji,
                burst_colors=burst_colors,
            )
            return [*reactions, reaction]

        await self._edit_reactions(added.message_id, add)

    async def _message_reaction_remove(self, event: DispatchEvent) -> None:
        removed = event.decode(MessageReactionRemove)
        mine = removed.user_id == self._self_id

        def remove(reactions: list[Reaction]) -> list[Reaction]:
            kept: list[Reaction] = []
            for reaction in reactions:
                if not _same_emoji(reaction.emoji, removed.emoji):
                    kept.append(reaction)
                    continue
                if reaction.count <= 1:
                    continue
                details = reaction.count_details
                kept.append(
                    msgspec.structs.replace(
                        reaction,
                        count=reaction.count - 1,
                        count_details=ReactionCountDetails(
                            burst=max(0, details.burst - int(removed.burst)),
                            normal=max(0, details.normal - int(not removed.burst)),
                        ),
                        me=reaction.me and not (mine and not removed.burst),
                        me_burst=reaction.me_burst and not (mine and removed.burst),
                    )
                )
            return kept

        await self._edit_reactions(removed.message_id, remove)

    async def _message_reaction_remove_all(self, event: DispatchEvent) -> None:
        cleared = event.decode(MessageReactionRemoveAll)

        def clear(reactions: list[Reaction]) -> list[Reaction]:
            del reactions
            return []

        await self._edit_reactions(cleared.message_id, clear)

    async def _message_reaction_remove_emoji(self, event: DispatchEvent) -> None:
        cleared = event.decode(MessageReactionRemoveEmoji)

        def without_emoji(reactions: list[Reaction]) -> list[Reaction]:
            return [reaction for reaction in reactions if not _same_emoji(reaction.emoji, cleared.emoji)]

        await self._edit_reactions(cleared.message_id, without_emoji)

    async def _message_upsert(self, event: DispatchEvent) -> None:
        # MESSAGE_UPDATE carries the full message, like MESSAGE_CREATE, so it replaces the entry.
        message = event.decode(MessageUpdate)
        scope = message.guild_id if isinstance(message.guild_id, Snowflake) else None
        await self._put(event, self._store.messages, message.id, message, scope)
        await self._put(event, self._store.users, message.author.id, message.author, None)

    async def _poll_vote_add(self, event: DispatchEvent) -> None:
        await self._count_vote(event.decode(MessagePollVoteAdd), 1)

    async def _poll_vote_remove(self, event: DispatchEvent) -> None:
        # MESSAGE_POLL_VOTE_REMOVE has the same fields as the add event.
        await self._count_vote(event.decode(MessagePollVoteAdd), -1)

    async def _count_vote(self, vote: MessagePollVoteAdd, change: int) -> None:
        mine = vote.user_id == self._self_id

        def recount(message: Message) -> Message:
            poll = message.poll
            if isinstance(poll, msgspec.UnsetType) or isinstance(poll.results, msgspec.UnsetType):
                # Without results the counts are unknown, and one vote does not make them known.
                return message
            counts = {count.id: count for count in poll.results.answer_counts}
            current = counts.get(vote.answer_id, PollAnswerCount(id=vote.answer_id, count=0, me_voted=False))
            updated = msgspec.structs.replace(
                current,
                count=max(0, current.count + change),
                me_voted=(change > 0) if mine else current.me_voted,
            )
            counts[vote.answer_id] = updated
            answer_counts = [count for count in counts.values() if count.count > 0 or count.me_voted]
            results = msgspec.structs.replace(poll.results, answer_counts=answer_counts)
            return msgspec.structs.replace(message, poll=msgspec.structs.replace(poll, results=results))

        await self._store.edit(self._store.messages, vote.message_id, recount)

    async def _presence_update(self, event: DispatchEvent) -> None:
        update = event.decode(PresenceUpdate)
        presence = Presence(
            user=update.user,
            status=update.status,
            activities=update.activities,
            client_status=update.client_status,
        )
        key = (update.guild_id, update.user.id)
        await self._put(event, self._store.presences, key, presence, update.guild_id)

    async def _ready(self, event: DispatchEvent) -> None:
        ready = event.decode(Ready)
        self._self_id = ready.user.id
        self._store.session_started(event.shard_id)
        for guild in ready.guilds:
            self._store.mark_unavailable(guild.id)
        await self._put(event, self._store.users, ready.user.id, ready.user, None)

    async def _resumed(self, event: DispatchEvent) -> None:
        self._store.session_resumed(event.shard_id)

    async def _scheduled_event_delete(self, event: DispatchEvent) -> None:
        await self._store.scheduled_events.delete(event.decode(GuildScheduledEvent).id)

    async def _scheduled_event_upsert(self, event: DispatchEvent) -> None:
        scheduled = event.decode(GuildScheduledEvent)
        await self._put(event, self._store.scheduled_events, scheduled.id, scheduled, scheduled.guild_id)

    async def _scheduled_event_user_add(self, event: DispatchEvent) -> None:
        await self._count_subscribers(event.decode(GuildScheduledEventUserAdd).guild_scheduled_event_id, 1)

    async def _scheduled_event_user_remove(self, event: DispatchEvent) -> None:
        # GUILD_SCHEDULED_EVENT_USER_REMOVE has the same fields as the add event.
        await self._count_subscribers(event.decode(GuildScheduledEventUserAdd).guild_scheduled_event_id, -1)

    async def _count_subscribers(self, event_id: Snowflake, change: int) -> None:
        def recount(scheduled: GuildScheduledEvent) -> GuildScheduledEvent:
            if isinstance(scheduled.user_count, msgspec.UnsetType):
                return scheduled
            return msgspec.structs.replace(scheduled, user_count=max(0, scheduled.user_count + change))

        await self._store.edit(self._store.scheduled_events, event_id, recount)

    async def _soundboard_sound_delete(self, event: DispatchEvent) -> None:
        await self._store.soundboard_sounds.delete(event.decode(GuildSoundboardSoundDelete).sound_id)

    async def _soundboard_sound_upsert(self, event: DispatchEvent) -> None:
        sound = event.decode(SoundboardSound)
        if isinstance(sound.guild_id, Snowflake):
            await self._store_sound(event, sound.guild_id, sound)

    async def _soundboard_sounds(self, event: DispatchEvent) -> None:
        # The answer to Request Soundboard Sounds: the guild's complete list.
        listed = event.decode(SoundboardSounds)
        current = {
            sound.sound_id: msgspec.structs.replace(sound, guild_id=listed.guild_id)
            for sound in listed.soundboard_sounds
        }
        await self._replace_scope(event, self._store.soundboard_sounds, listed.guild_id, current)

    async def _soundboard_sounds_update(self, event: DispatchEvent) -> None:
        # Several sounds changed; the others are untouched, so nothing is removed.
        update = event.decode(GuildSoundboardSoundsUpdate)
        for sound in update.soundboard_sounds:
            await self._store_sound(event, update.guild_id, sound)

    async def _stage_instance_delete(self, event: DispatchEvent) -> None:
        await self._store.stage_instances.delete(event.decode(StageInstance).id)

    async def _stage_instance_upsert(self, event: DispatchEvent) -> None:
        stage = event.decode(StageInstance)
        await self._put(event, self._store.stage_instances, stage.id, stage, stage.guild_id)

    async def _thread_list_sync(self, event: DispatchEvent) -> None:
        sync = event.decode(ThreadListSync)
        active = {thread.id for thread in sync.threads}
        parents = set(sync.channel_ids) if sync.channel_ids is not UNSET else None
        for key, entry in await self._store.channels.scoped(sync.guild_id):
            channel = entry.value
            if not channel.type.is_thread or key in active:
                continue
            parent = channel.parent_id if isinstance(channel.parent_id, Snowflake) else None
            if parents is None or parent in parents:
                await self._store.channels.delete(key)
        for thread in sync.threads:
            await self._put(event, self._store.channels, thread.id, thread, sync.guild_id)

    async def _thread_members_update(self, event: DispatchEvent) -> None:
        update = event.decode(ThreadMembersUpdate)
        added = update.added_members if not isinstance(update.added_members, msgspec.UnsetType) else []
        removed = (
            update.removed_member_ids if not isinstance(update.removed_member_ids, msgspec.UnsetType) else []
        )
        joined = next((member for member in added if member.user_id == self._self_id), None)
        left = self._self_id is not None and self._self_id in removed

        def recount(thread: Channel) -> Channel:
            membership = thread.member
            if joined is not None:
                membership = _membership(joined)
            elif left:
                membership = UNSET
            return msgspec.structs.replace(thread, member_count=update.member_count, member=membership)

        await self._store.edit(self._store.channels, update.id, recount)
        for member in added:
            # Added thread members carry their guild member and presence in this event only.
            if not isinstance(member.member, msgspec.UnsetType):
                await self._store_member(event, update.guild_id, member.member)
            if member.presence is not None and not isinstance(member.presence, msgspec.UnsetType):
                key = (update.guild_id, member.presence.user.id)
                await self._put(event, self._store.presences, key, member.presence, update.guild_id)

    async def _thread_member_update(self, event: DispatchEvent) -> None:
        # The bot's own membership of a thread changed.
        update = event.decode(ThreadMemberUpdate)
        membership = _membership(update)

        def join(thread: Channel) -> Channel:
            return msgspec.structs.replace(thread, member=membership)

        if isinstance(update.id, Snowflake):
            await self._store.edit(self._store.channels, update.id, join)

    async def _user_update(self, event: DispatchEvent) -> None:
        user = event.decode(User)
        await self._put(event, self._store.users, user.id, user, None)

    async def _voice_state_update(self, event: DispatchEvent) -> None:
        voice_state = event.decode(VoiceState)
        if isinstance(voice_state.guild_id, Snowflake):
            await self._store_voice_state(event, voice_state.guild_id, voice_state)

    async def _count_members(self, guild_id: Snowflake, change: int) -> None:
        def recount(guild: CachedGuild) -> CachedGuild:
            if isinstance(guild.member_count, msgspec.UnsetType):
                return guild
            return msgspec.structs.replace(guild, member_count=max(0, guild.member_count + change))

        await self._store.edit(self._store.guilds, guild_id, recount)

    async def _edit_reactions(
        self, message_id: Snowflake, change: Callable[[list[Reaction]], list[Reaction]]
    ) -> None:
        def update(message: Message) -> Message:
            current = list(message.reactions) if message.reactions is not UNSET else []
            return msgspec.structs.replace(message, reactions=change(current))

        await self._store.edit(self._store.messages, message_id, update)

    async def _store_guild(self, event: DispatchEvent, guild: Guild, cached: CachedGuild) -> None:
        await self._store_guild_contents(event, guild)
        await self._put(event, self._store.guilds, guild.id, cached, guild.id)

    async def _store_guild_contents(self, event: DispatchEvent, guild: Guild) -> None:
        """A guild's roles, emojis and stickers, which live in their own collections."""
        for role in guild.roles:
            await self._put(event, self._store.roles, role.id, role, guild.id)
        for emoji in guild.emojis:
            if emoji.id is not None:
                await self._put(event, self._store.emojis, emoji.id, emoji, guild.id)
        if not isinstance(guild.stickers, msgspec.UnsetType):
            for sticker in guild.stickers:
                await self._put(event, self._store.stickers, sticker.id, sticker, guild.id)

    async def _replace_scope[V](
        self,
        event: DispatchEvent,
        collection: CacheCollection[Snowflake, V],
        guild_id: Snowflake,
        current: dict[Snowflake, V],
    ) -> None:
        """Make `current` the guild's complete set in `collection` (a full list event)."""
        for key, _ in await collection.scoped(guild_id):
            if key not in current:
                await collection.delete(key)
        for key, value in current.items():
            await self._put(event, collection, key, value, guild_id)

    async def _store_sound(self, event: DispatchEvent, guild_id: Snowflake, sound: SoundboardSound) -> None:
        # Sounds listed in `GUILD_CREATE` and `SOUNDBOARD_SOUNDS` leave out the guild they belong to.
        if isinstance(sound.guild_id, msgspec.UnsetType):
            sound = msgspec.structs.replace(sound, guild_id=guild_id)
        await self._put(event, self._store.soundboard_sounds, sound.sound_id, sound, guild_id)

    async def _store_member(self, event: DispatchEvent, guild_id: Snowflake, member: GuildMember) -> None:
        if isinstance(member.user, msgspec.UnsetType):
            return
        await self._put(event, self._store.users, member.user.id, member.user, None)
        await self._put(event, self._store.members, (guild_id, member.user.id), member, guild_id)

    async def _store_voice_state(
        self, event: DispatchEvent, guild_id: Snowflake, voice_state: VoiceState
    ) -> None:
        key = (guild_id, voice_state.user_id)
        if voice_state.channel_id is None:
            await self._store.voice_states.delete(key)
            return
        await self._put(event, self._store.voice_states, key, voice_state, guild_id)
        if not isinstance(voice_state.member, msgspec.UnsetType):
            await self._store_member(event, guild_id, voice_state.member)
