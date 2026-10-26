"""Turning gateway dispatches into events with models, with the cache kept in step.

For each dispatch the translator reads what the cache held before (the `before` of update events),
lets `CacheUpdater` apply the dispatch, and then emits the events with models. Raw events (`on_raw_*`)
carry the payload and are emitted whether or not anything was cached, so nothing is ever dropped
because the cache did not hold it; the friendlier events that need cached state (`on_message_edit`
with its `before`) fire only when that state is known.

Discord: https://docs.discord.com/developers/events/gateway-events#receive-events
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, final

from msgspec import UnsetType

from shoal.cache.updater import CacheUpdater
from shoal.core.dispatch import DispatchEvent
from shoal.core.snowflake import Snowflake
from shoal.models.base import Object
from shoal.models.channel import GuildChannel, channel_from_payload, resolve_channel, resolve_guild_channel
from shoal.models.emoji import Emoji
from shoal.models.guild import Guild
from shoal.models.member import Member
from shoal.models.message import Message, Reaction
from shoal.models.role import Role
from shoal.models.state import State
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads.channel import Channel
from shoal.payloads.emoji import Emoji as EmojiPayload
from shoal.payloads.gateway_events import (
    DISPATCH_PAYLOADS,
    ChannelPinsUpdate,
    GuildBanAdd,
    GuildCreate,
    GuildDelete,
    GuildEmojisUpdate,
    GuildIntegrationsUpdate,
    GuildMemberAdd,
    GuildMemberRemove,
    GuildMemberUpdate,
    GuildRoleCreate,
    GuildRoleDelete,
    GuildScheduledEventUserAdd,
    GuildSoundboardSoundDelete,
    GuildStickersUpdate,
    MessageDelete,
    MessageDeleteBulk,
    MessageReactionAdd,
    MessageReactionRemove,
    MessageReactionRemoveAll,
    MessageReactionRemoveEmoji,
    MessageUpdate,
    PresenceUpdate,
    ThreadCreate,
    TypingStart,
    WebhooksUpdate,
)
from shoal.payloads.guild import Guild as GuildPayload
from shoal.payloads.guild import UnavailableGuild
from shoal.payloads.scheduled_event import GuildScheduledEvent
from shoal.payloads.soundboard import SoundboardSound
from shoal.payloads.stage_instance import StageInstance
from shoal.payloads.user import User as UserPayload
from shoal.payloads.voice import VoiceState

if TYPE_CHECKING:
    from shoal.payloads.base import Payload


def _same_emoji(left: EmojiPayload, right: EmojiPayload) -> bool:
    """Custom emojis match by ID, unicode ones by name (the gateway sends them with fewer fields)."""
    if left.id is not None or right.id is not None:
        return left.id == right.id
    return left.name == right.name


type Emit = Callable[..., None]
"""Dispatches one event to listeners: `emit("message", message)` runs every `on_message`."""
type _Handler = Callable[[DispatchEvent], Awaitable[None]]

_RAW_ONLY: Final = {
    "APPLICATION_COMMAND_PERMISSIONS_UPDATE": "raw_app_command_permissions_update",
    "AUTO_MODERATION_ACTION_EXECUTION": "automod_action",
    "AUTO_MODERATION_RULE_CREATE": "automod_rule_create",
    "AUTO_MODERATION_RULE_DELETE": "automod_rule_delete",
    "AUTO_MODERATION_RULE_UPDATE": "automod_rule_update",
    "CHANNEL_INFO": "raw_channel_info",
    "ENTITLEMENT_CREATE": "entitlement_create",
    "ENTITLEMENT_DELETE": "entitlement_delete",
    "ENTITLEMENT_UPDATE": "entitlement_update",
    "GUILD_AUDIT_LOG_ENTRY_CREATE": "audit_log_entry_create",
    "INTEGRATION_CREATE": "integration_create",
    "INTEGRATION_DELETE": "raw_integration_delete",
    "INTEGRATION_UPDATE": "integration_update",
    "INVITE_CREATE": "invite_create",
    "INVITE_DELETE": "invite_delete",
    "MESSAGE_POLL_VOTE_ADD": "raw_poll_vote_add",
    "MESSAGE_POLL_VOTE_REMOVE": "raw_poll_vote_remove",
    "RATE_LIMITED": "rate_limited",
    "SUBSCRIPTION_CREATE": "subscription_create",
    "SUBSCRIPTION_DELETE": "subscription_delete",
    "SUBSCRIPTION_UPDATE": "subscription_update",
    "THREAD_LIST_SYNC": "raw_thread_list_sync",
    "THREAD_MEMBERS_UPDATE": "raw_thread_members_update",
    "THREAD_MEMBER_UPDATE": "raw_thread_member_update",
    "VOICE_CHANNEL_EFFECT_SEND": "voice_channel_effect",
    "VOICE_CHANNEL_START_TIME_UPDATE": "raw_voice_channel_start_time_update",
    "VOICE_CHANNEL_STATUS_UPDATE": "raw_voice_channel_status_update",
    "VOICE_SERVER_UPDATE": "voice_server_update",
}
"""Dispatches whose event carries the payload as it is, by dispatch name."""


@final
class EventTranslator:
    """Applies dispatches to the cache and emits events with models for them.

    `READY`, `RESUMED` and `INTERACTION_CREATE` are left to the client, which tracks readiness and
    routes interactions; `handles` says which dispatches this class takes.
    """

    __slots__ = ("_emit", "_handlers", "_state", "_updater")

    def __init__(self, state: State, updater: CacheUpdater, emit: Emit) -> None:
        """Translate into `emit`, keeping `updater`'s cache current."""
        self._state: State = state
        self._updater: CacheUpdater = updater
        self._emit: Emit = emit
        self._handlers: dict[str, _Handler] = {
            "CHANNEL_CREATE": self._channel_create,
            "CHANNEL_DELETE": self._channel_delete,
            "CHANNEL_PINS_UPDATE": self._channel_pins_update,
            "CHANNEL_UPDATE": self._channel_update,
            "GUILD_BAN_ADD": self._guild_ban_add,
            "GUILD_BAN_REMOVE": self._guild_ban_remove,
            "GUILD_CREATE": self._guild_create,
            "GUILD_DELETE": self._guild_delete,
            "GUILD_EMOJIS_UPDATE": self._guild_emojis_update,
            "GUILD_INTEGRATIONS_UPDATE": self._guild_integrations_update,
            "GUILD_MEMBERS_CHUNK": self._apply_only,
            "GUILD_MEMBER_ADD": self._guild_member_add,
            "GUILD_MEMBER_REMOVE": self._guild_member_remove,
            "GUILD_MEMBER_UPDATE": self._guild_member_update,
            "GUILD_ROLE_CREATE": self._guild_role_create,
            "GUILD_ROLE_DELETE": self._guild_role_delete,
            "GUILD_ROLE_UPDATE": self._guild_role_update,
            "GUILD_SCHEDULED_EVENT_CREATE": self._scheduled_event_create,
            "GUILD_SCHEDULED_EVENT_DELETE": self._scheduled_event_delete,
            "GUILD_SCHEDULED_EVENT_UPDATE": self._scheduled_event_update,
            "GUILD_SCHEDULED_EVENT_USER_ADD": self._scheduled_event_user_add,
            "GUILD_SCHEDULED_EVENT_USER_REMOVE": self._scheduled_event_user_remove,
            "GUILD_SOUNDBOARD_SOUNDS_UPDATE": self._soundboard_sounds_update,
            "GUILD_SOUNDBOARD_SOUND_CREATE": self._soundboard_sound_create,
            "GUILD_SOUNDBOARD_SOUND_DELETE": self._soundboard_sound_delete,
            "GUILD_SOUNDBOARD_SOUND_UPDATE": self._soundboard_sound_update,
            "GUILD_STICKERS_UPDATE": self._guild_stickers_update,
            "GUILD_UPDATE": self._guild_update,
            "MESSAGE_CREATE": self._message_create,
            "MESSAGE_DELETE": self._message_delete,
            "MESSAGE_DELETE_BULK": self._message_delete_bulk,
            "MESSAGE_REACTION_ADD": self._reaction_add,
            "MESSAGE_REACTION_REMOVE": self._reaction_remove,
            "MESSAGE_REACTION_REMOVE_ALL": self._reaction_remove_all,
            "MESSAGE_REACTION_REMOVE_EMOJI": self._reaction_remove_emoji,
            "MESSAGE_UPDATE": self._message_update,
            "PRESENCE_UPDATE": self._presence_update,
            "SOUNDBOARD_SOUNDS": self._apply_only,
            "STAGE_INSTANCE_CREATE": self._stage_instance_create,
            "STAGE_INSTANCE_DELETE": self._stage_instance_delete,
            "STAGE_INSTANCE_UPDATE": self._stage_instance_update,
            "THREAD_CREATE": self._thread_create,
            "THREAD_DELETE": self._thread_delete,
            "THREAD_UPDATE": self._thread_update,
            "TYPING_START": self._typing_start,
            "USER_UPDATE": self._user_update,
            "VOICE_STATE_UPDATE": self._voice_state_update,
            "WEBHOOKS_UPDATE": self._webhooks_update,
        }
        for name in _RAW_ONLY:
            self._handlers[name] = self._raw

    @property
    def handles(self) -> frozenset[str]:
        """The dispatch names this translator emits events for."""
        return frozenset(self._handlers)

    async def translate(self, event: DispatchEvent) -> None:
        """Apply `event` to the cache and emit its events. Unknown dispatches only reach the cache."""
        handler = self._handlers.get(event.name)
        if handler is None:
            await self._updater.apply(event)
            return
        await handler(event)

    def _peek_member(self, guild_id: int, user_id: int) -> Member | None:
        return Member.from_cache(self._state, guild_id, user_id)

    def _guild_or_object(self, guild_id: int) -> Guild | Object:
        return Guild.from_cache(self._state, guild_id) or Object(guild_id)

    def _user_or_object(self, guild_id: int | None, user_id: int) -> Member | User | Object:
        if guild_id is not None and (member := self._peek_member(guild_id, user_id)) is not None:
            return member
        return User.from_cache(self._state, user_id) or Object(user_id)

    def _message(self, message_id: int) -> Message | None:
        data = self._state.cache.peek(self._state.cache.messages, Snowflake(message_id))
        return Message(self._state, data) if data is not None else None

    async def _apply_only(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)

    async def _raw(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        payload: Payload = event.decode(DISPATCH_PAYLOADS[event.name])
        self._emit(_RAW_ONLY[event.name], payload)

    async def _guild_create(self, event: DispatchEvent) -> None:
        status = event.decode(UnavailableGuild)
        if status.unavailable is True:
            await self._updater.apply(event)
            return
        # A guild the bot was already in (listed in READY, back from an outage,
        # or cached) becomes available; any other guild was just joined.
        cache = self._state.cache
        known = cache.is_unavailable(status.id) or cache.peek(cache.guilds, status.id) is not None
        await self._updater.apply(event)
        guild = Guild.from_cache(self._state, status.id) or Guild(self._state, event.decode(GuildCreate))
        self._emit("guild_available" if known else "guild_join", guild)

    async def _guild_update(self, event: DispatchEvent) -> None:
        data = event.decode(GuildPayload)
        before = Guild.from_cache(self._state, data.id)
        await self._updater.apply(event)
        after = Guild.from_cache(self._state, data.id) or Guild(self._state, data)
        if before is not None:
            self._emit("guild_update", before, after)

    async def _guild_delete(self, event: DispatchEvent) -> None:
        deleted = event.decode(GuildDelete)
        guild = Guild.from_cache(self._state, deleted.id)
        await self._updater.apply(event)
        if guild is None:
            return
        self._emit("guild_unavailable" if deleted.unavailable is True else "guild_remove", guild)

    async def _guild_ban_add(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        ban = event.decode(GuildBanAdd)
        self._emit("member_ban", self._guild_or_object(ban.guild_id), User(self._state, ban.user))

    async def _guild_ban_remove(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        ban = event.decode(GuildBanAdd)
        self._emit("member_unban", self._guild_or_object(ban.guild_id), User(self._state, ban.user))

    async def _guild_emojis_update(self, event: DispatchEvent) -> None:
        update = event.decode(GuildEmojisUpdate)
        guild = self._guild_or_object(update.guild_id)
        before = guild.emojis if isinstance(guild, Guild) else []
        await self._updater.apply(event)
        after = [
            Emoji(self._state, emoji, update.guild_id) for emoji in update.emojis if emoji.id is not None
        ]
        self._emit("guild_emojis_update", guild, before, after)

    async def _guild_stickers_update(self, event: DispatchEvent) -> None:
        update = event.decode(GuildStickersUpdate)
        guild = self._guild_or_object(update.guild_id)
        before = guild.stickers if isinstance(guild, Guild) else []
        await self._updater.apply(event)
        self._emit("guild_stickers_update", guild, before, list(update.stickers))

    async def _guild_integrations_update(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        update = event.decode(GuildIntegrationsUpdate)
        self._emit("guild_integrations_update", self._guild_or_object(update.guild_id))

    async def _channel_create(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        channel = channel_from_payload(self._state, event.decode(Channel))
        self._emit(
            "guild_channel_create" if isinstance(channel, GuildChannel) else "private_channel_create", channel
        )

    async def _channel_update(self, event: DispatchEvent) -> None:
        data = event.decode(Channel)
        before = resolve_guild_channel(self._state, data.id)
        await self._updater.apply(event)
        after = channel_from_payload(self._state, data)
        if before is not None:
            name = "guild_channel_update" if isinstance(after, GuildChannel) else "private_channel_update"
            self._emit(name, before, after)

    async def _channel_delete(self, event: DispatchEvent) -> None:
        data = event.decode(Channel)
        cached = resolve_guild_channel(self._state, data.id)
        await self._updater.apply(event)
        channel = cached or channel_from_payload(self._state, data)
        self._emit(
            "guild_channel_delete" if isinstance(channel, GuildChannel) else "private_channel_delete", channel
        )

    async def _channel_pins_update(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        pins = event.decode(ChannelPinsUpdate)
        guild_id = pins.guild_id if isinstance(pins.guild_id, Snowflake) else None
        channel = resolve_channel(self._state, pins.channel_id, guild_id)
        last = pins.last_pin_timestamp if isinstance(pins.last_pin_timestamp, datetime) else None
        self._emit("guild_channel_pins_update" if guild_id else "private_channel_pins_update", channel, last)

    async def _thread_create(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        data = event.decode(ThreadCreate)
        thread = Thread(self._state, data)
        self._emit("thread_create" if data.newly_created is True else "thread_join", thread)

    async def _thread_update(self, event: DispatchEvent) -> None:
        data = event.decode(Channel)
        before = resolve_guild_channel(self._state, data.id)
        await self._updater.apply(event)
        if isinstance(before, Thread):
            self._emit("thread_update", before, Thread(self._state, data))

    async def _thread_delete(self, event: DispatchEvent) -> None:
        data = event.decode(Channel)
        before = resolve_guild_channel(self._state, data.id)
        await self._updater.apply(event)
        self._emit("raw_thread_delete", data)
        if isinstance(before, Thread):
            self._emit("thread_delete", before)

    async def _webhooks_update(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        update = event.decode(WebhooksUpdate)
        channel = resolve_guild_channel(self._state, update.channel_id) or Object(update.channel_id)
        self._emit("webhooks_update", channel)

    async def _message_create(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        self._emit("message", Message(self._state, event.decode(MessageUpdate)))

    async def _message_update(self, event: DispatchEvent) -> None:
        data = event.decode(MessageUpdate)
        before = self._message(data.id)
        await self._updater.apply(event)
        self._emit("raw_message_edit", data)
        if before is not None:
            self._emit("message_edit", before, Message(self._state, data))

    async def _message_delete(self, event: DispatchEvent) -> None:
        deleted = event.decode(MessageDelete)
        cached = self._message(deleted.id)
        await self._updater.apply(event)
        self._emit("raw_message_delete", deleted)
        if cached is not None:
            self._emit("message_delete", cached)

    async def _message_delete_bulk(self, event: DispatchEvent) -> None:
        deleted = event.decode(MessageDeleteBulk)
        cached = [message for message_id in deleted.ids if (message := self._message(message_id)) is not None]
        await self._updater.apply(event)
        self._emit("raw_bulk_message_delete", deleted)
        if cached:
            self._emit("bulk_message_delete", cached)

    def _reaction_on(self, message_id: int, emoji: EmojiPayload) -> Reaction | None:
        message = self._message(message_id)
        if message is None:
            return None
        return next(
            (reaction for reaction in message.reactions if _same_emoji(reaction.payload.emoji, emoji)), None
        )

    async def _reaction_add(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        added = event.decode(MessageReactionAdd)
        self._emit("raw_reaction_add", added)
        reaction = self._reaction_on(added.message_id, added.emoji)
        if reaction is not None:
            guild_id = added.guild_id if isinstance(added.guild_id, Snowflake) else None
            self._emit("reaction_add", reaction, self._user_or_object(guild_id, added.user_id))

    async def _reaction_remove(self, event: DispatchEvent) -> None:
        removed = event.decode(MessageReactionRemove)
        before = self._reaction_on(removed.message_id, removed.emoji)
        await self._updater.apply(event)
        self._emit("raw_reaction_remove", removed)
        if before is not None:
            after = self._reaction_on(removed.message_id, removed.emoji) or before
            guild_id = removed.guild_id if isinstance(removed.guild_id, Snowflake) else None
            self._emit("reaction_remove", after, self._user_or_object(guild_id, removed.user_id))

    async def _reaction_remove_all(self, event: DispatchEvent) -> None:
        cleared = event.decode(MessageReactionRemoveAll)
        message = self._message(cleared.message_id)
        await self._updater.apply(event)
        self._emit("raw_reaction_clear", cleared)
        if message is not None:
            self._emit("reaction_clear", message, message.reactions)

    async def _reaction_remove_emoji(self, event: DispatchEvent) -> None:
        cleared = event.decode(MessageReactionRemoveEmoji)
        before = self._reaction_on(cleared.message_id, cleared.emoji)
        await self._updater.apply(event)
        self._emit("raw_reaction_clear_emoji", cleared)
        if before is not None:
            self._emit("reaction_clear_emoji", before)

    async def _typing_start(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        typing = event.decode(TypingStart)
        self._emit("raw_typing", typing)
        guild_id = typing.guild_id if isinstance(typing.guild_id, Snowflake) else None
        channel = resolve_channel(self._state, typing.channel_id, guild_id)
        who: Member | User | Object
        if guild_id is not None and not isinstance(typing.member, UnsetType):
            who = Member(self._state, typing.member, guild_id)
        else:
            who = self._user_or_object(guild_id, typing.user_id)
        self._emit("typing", channel, who, datetime.fromtimestamp(typing.timestamp, tz=UTC))

    async def _guild_member_add(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        added = event.decode(GuildMemberAdd)
        self._emit("member_join", Member(self._state, added, added.guild_id))

    async def _guild_member_remove(self, event: DispatchEvent) -> None:
        removed = event.decode(GuildMemberRemove)
        cached = self._peek_member(removed.guild_id, removed.user.id)
        await self._updater.apply(event)
        self._emit("raw_member_remove", removed)
        if cached is not None:
            self._emit("member_remove", cached)

    async def _guild_member_update(self, event: DispatchEvent) -> None:
        update = event.decode(GuildMemberUpdate)
        before = self._peek_member(update.guild_id, update.user.id)
        await self._updater.apply(event)
        self._emit("raw_member_update", update)
        after = self._peek_member(update.guild_id, update.user.id)
        if before is not None and after is not None:
            self._emit("member_update", before, after)

    async def _guild_role_create(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        created = event.decode(GuildRoleCreate)
        self._emit("guild_role_create", Role(self._state, created.role, created.guild_id))

    async def _guild_role_update(self, event: DispatchEvent) -> None:
        updated = event.decode(GuildRoleCreate)
        before = Role.from_cache(self._state, updated.role.id)
        await self._updater.apply(event)
        if before is not None:
            self._emit("guild_role_update", before, Role(self._state, updated.role, updated.guild_id))

    async def _guild_role_delete(self, event: DispatchEvent) -> None:
        deleted = event.decode(GuildRoleDelete)
        before = Role.from_cache(self._state, deleted.role_id)
        await self._updater.apply(event)
        if before is not None:
            self._emit("guild_role_delete", before)

    async def _presence_update(self, event: DispatchEvent) -> None:
        update = event.decode(PresenceUpdate)
        before = self._peek_member(update.guild_id, update.user.id)
        await self._updater.apply(event)
        self._emit("raw_presence_update", update)
        after = self._peek_member(update.guild_id, update.user.id)
        if before is not None and after is not None:
            self._emit("presence_update", before, after)

    async def _user_update(self, event: DispatchEvent) -> None:
        data = event.decode(UserPayload)
        before = User.from_cache(self._state, data.id)
        await self._updater.apply(event)
        if before is not None:
            self._emit("user_update", before, User(self._state, data))

    async def _voice_state_update(self, event: DispatchEvent) -> None:
        data = event.decode(VoiceState)
        if not isinstance(data.guild_id, Snowflake):
            await self._updater.apply(event)
            return
        guild_id = data.guild_id
        before = self._state.cache.peek(self._state.cache.voice_states, (guild_id, data.user_id))
        await self._updater.apply(event)
        who: Member | User | Object
        if not isinstance(data.member, UnsetType) and not isinstance(data.member.user, UnsetType):
            who = Member(self._state, data.member, guild_id)
        else:
            who = self._user_or_object(guild_id, data.user_id)
        after = data if data.channel_id is not None else None
        self._emit("voice_state_update", who, before, after)

    async def _scheduled_event_create(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        self._emit("scheduled_event_create", event.decode(GuildScheduledEvent))

    async def _scheduled_event_update(self, event: DispatchEvent) -> None:
        data = event.decode(GuildScheduledEvent)
        before = self._state.cache.peek(self._state.cache.scheduled_events, data.id)
        await self._updater.apply(event)
        if before is not None:
            self._emit("scheduled_event_update", before, data)

    async def _scheduled_event_delete(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        self._emit("scheduled_event_delete", event.decode(GuildScheduledEvent))

    async def _scheduled_event_user_add(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        added = event.decode(GuildScheduledEventUserAdd)
        self._emit("raw_scheduled_event_user_add", added)
        scheduled = self._state.cache.peek(self._state.cache.scheduled_events, added.guild_scheduled_event_id)
        if scheduled is not None:
            self._emit(
                "scheduled_event_user_add", scheduled, self._user_or_object(added.guild_id, added.user_id)
            )

    async def _scheduled_event_user_remove(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        removed = event.decode(GuildScheduledEventUserAdd)
        self._emit("raw_scheduled_event_user_remove", removed)
        scheduled = self._state.cache.peek(
            self._state.cache.scheduled_events, removed.guild_scheduled_event_id
        )
        if scheduled is not None:
            who = self._user_or_object(removed.guild_id, removed.user_id)
            self._emit("scheduled_event_user_remove", scheduled, who)

    async def _stage_instance_create(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        self._emit("stage_instance_create", event.decode(StageInstance))

    async def _stage_instance_update(self, event: DispatchEvent) -> None:
        data = event.decode(StageInstance)
        before = self._state.cache.peek(self._state.cache.stage_instances, data.id)
        await self._updater.apply(event)
        if before is not None:
            self._emit("stage_instance_update", before, data)

    async def _stage_instance_delete(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        self._emit("stage_instance_delete", event.decode(StageInstance))

    async def _soundboard_sound_create(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
        self._emit("soundboard_sound_create", event.decode(SoundboardSound))

    async def _soundboard_sound_update(self, event: DispatchEvent) -> None:
        data = event.decode(SoundboardSound)
        before = self._state.cache.peek(self._state.cache.soundboard_sounds, data.sound_id)
        await self._updater.apply(event)
        if before is not None:
            self._emit("soundboard_sound_update", before, data)

    async def _soundboard_sound_delete(self, event: DispatchEvent) -> None:
        deleted = event.decode(GuildSoundboardSoundDelete)
        before = self._state.cache.peek(self._state.cache.soundboard_sounds, deleted.sound_id)
        await self._updater.apply(event)
        self._emit("raw_soundboard_sound_delete", deleted)
        if before is not None:
            self._emit("soundboard_sound_delete", before)

    async def _soundboard_sounds_update(self, event: DispatchEvent) -> None:
        await self._updater.apply(event)
