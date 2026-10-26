"""A small guild for model tests, cached through the real `CacheUpdater`, and a REST double.

world = await World.started()
member = world.guild().get_member(ALICE)
world.transport.queue(200, MEMBER_JSON)
await member.edit(nick="new")
assert world.last_request() == ("PATCH", "/guilds/10/members/3", {"nick": "new"})
"""

from typing import Self, cast, override

import msgspec

from shoal.cache.store import CacheStore
from shoal.cache.updater import CacheUpdater
from shoal.core.dispatch import DispatchEvent
from shoal.models.guild import Guild
from shoal.models.state import ComponentView, State, ViewRegistry
from shoal.payloads import ActionRow, Button, ButtonStyle, Intents, MessageComponent
from tests.support.fakes import FakeClock, FakeTransport
from tests.support.rest import API, make_client

GUILD = 10
BOT = 1
OWNER = 2
ALICE = 3
BOB = 4
APPLICATION = 7

EVERYONE = GUILD
MODS = 20
RED = 21

CATEGORY = 40
GENERAL = 41
VOICE = 42
STAGE = 43
FORUM = 44
THREAD = 45
ANNOUNCEMENTS = 46

EMOJI = 30

VIEW_SEND_HISTORY = (1 << 10) | (1 << 11) | (1 << 16)
"""View Channel, Send Messages, Read Message History."""
KICK_BAN = (1 << 1) | (1 << 2)
SEND_MESSAGES = 1 << 11

type Json = dict[str, object]


def user(user_id: int, name: str, *, global_name: str | None = None, avatar: str | None = None) -> Json:
    return {
        "id": str(user_id),
        "username": name,
        "discriminator": "0",
        "global_name": global_name,
        "avatar": avatar,
    }


def member(
    user_id: int,
    name: str,
    *,
    roles: list[int] | None = None,
    global_name: str | None = None,
    **extra: object,
) -> Json:
    data: Json = {
        "user": user(user_id, name, global_name=global_name),
        "roles": [str(role) for role in roles or []],
        "joined_at": "2024-01-01T00:00:00+00:00",
        "deaf": False,
        "mute": False,
        "flags": 0,
    }
    return data | extra


def role(
    role_id: int, name: str, *, position: int, permissions: int = 0, color: int = 0, hoist: bool = False
) -> Json:
    return {
        "id": str(role_id),
        "name": name,
        "color": color,
        "colors": {"primary_color": color, "secondary_color": None, "tertiary_color": None},
        "hoist": hoist,
        "position": position,
        "permissions": str(permissions),
        "managed": False,
        "mentionable": False,
        "flags": 0,
    }


def channel(
    channel_id: int, kind: int, name: str, *, position: int = 0, parent: int | None = None, **extra: object
) -> Json:
    data: Json = {
        "id": str(channel_id),
        "type": kind,
        "guild_id": str(GUILD),
        "name": name,
        "position": position,
        "parent_id": str(parent) if parent else None,
        "permission_overwrites": [],
    }
    return data | extra


def message(
    message_id: int, *, channel_id: int = GENERAL, author: Json | None = None, **extra: object
) -> Json:
    data: Json = {
        "id": str(message_id),
        "channel_id": str(channel_id),
        "author": author or user(ALICE, "alice", global_name="Alice"),
        "content": "hello",
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
    return data | extra


def guild_create() -> Json:
    deny_send = {"id": str(EVERYONE), "type": 0, "allow": "0", "deny": str(SEND_MESSAGES)}
    allow_mods = {"id": str(MODS), "type": 0, "allow": str(SEND_MESSAGES), "deny": "0"}
    data: Json = {
        "id": str(GUILD),
        "name": "Shoal Test",
        "icon": "a_animatedicon",
        "splash": None,
        "discovery_splash": None,
        "owner_id": str(OWNER),
        "afk_channel_id": str(VOICE),
        "afk_timeout": 300,
        "verification_level": 1,
        "default_message_notifications": 0,
        "explicit_content_filter": 0,
        "roles": [
            role(EVERYONE, "@everyone", position=0, permissions=VIEW_SEND_HISTORY),
            role(MODS, "mods", position=2, permissions=KICK_BAN),
            role(RED, "red", position=1, color=0xFF0000, hoist=True),
        ],
        "emojis": [{"id": str(EMOJI), "name": "wave", "animated": False, "roles": [str(MODS)]}],
        "features": ["COMMUNITY"],
        "mfa_level": 0,
        "application_id": None,
        "system_channel_id": str(GENERAL),
        "system_channel_flags": 0,
        "rules_channel_id": None,
        "vanity_url_code": None,
        "description": None,
        "banner": None,
        "premium_tier": 1,
        "preferred_locale": "en-US",
        "public_updates_channel_id": None,
        "nsfw_level": 0,
        "premium_progress_bar_enabled": False,
        "safety_alerts_channel_id": None,
        "joined_at": "2024-01-01T00:00:00+00:00",
        "large": False,
        "member_count": 4,
        "members": [
            member(BOT, "shoalbot"),
            member(OWNER, "owner"),
            member(ALICE, "alice", roles=[RED], nick="Ally", global_name="Alice"),
            member(BOB, "bob", roles=[MODS]),
        ],
        "channels": [
            channel(CATEGORY, 4, "Text", position=0),
            channel(
                GENERAL,
                0,
                "general",
                position=1,
                parent=CATEGORY,
                permission_overwrites=[deny_send, allow_mods],
            ),
            channel(ANNOUNCEMENTS, 5, "news", position=2, parent=CATEGORY),
            channel(VOICE, 2, "Voice", position=3, bitrate=96000, user_limit=5),
            channel(STAGE, 13, "Stage", position=4),
            channel(FORUM, 15, "help", position=5, available_tags=[]),
        ],
        "threads": [
            {
                "id": str(THREAD),
                "type": 11,
                "guild_id": str(GUILD),
                "name": "a thread",
                "parent_id": str(GENERAL),
                "owner_id": str(ALICE),
                "message_count": 3,
                "member_count": 2,
                "thread_metadata": {
                    "archived": False,
                    "auto_archive_duration": 60,
                    "archive_timestamp": "2024-01-01T00:00:00+00:00",
                    "locked": False,
                },
            }
        ],
        "voice_states": [
            {
                "channel_id": str(VOICE),
                "user_id": str(BOB),
                "session_id": "s",
                "deaf": False,
                "mute": False,
                "self_deaf": False,
                "self_mute": True,
                "self_video": False,
                "suppress": False,
                "request_to_speak_timestamp": None,
            }
        ],
        "presences": [
            {
                "user": {"id": str(ALICE)},
                "status": "idle",
                "activities": [],
                "client_status": {"mobile": "idle"},
            }
        ],
        "stage_instances": [
            {
                "id": "50",
                "guild_id": str(GUILD),
                "channel_id": str(STAGE),
                "topic": "Town hall",
                "privacy_level": 2,
                "discoverable_disabled": False,
                "guild_scheduled_event_id": None,
            }
        ],
    }
    return data


class StaticView(ComponentView):
    """A view with fixed components; `dispatchable` says whether it wants their interactions."""

    def __init__(self, *components: MessageComponent, dispatchable: bool = True) -> None:
        self.components = list(components)
        self.dispatchable = dispatchable

    @override
    def to_components(self) -> list[MessageComponent]:
        return self.components

    @override
    def is_dispatchable(self) -> bool:
        return self.dispatchable


ROW = ActionRow(components=[Button(style=ButtonStyle.PRIMARY, custom_id="ok", label="OK")])
ROW_VIEW = StaticView(ROW)
LINK_VIEW = StaticView(
    ActionRow(components=[Button(style=ButtonStyle.LINK, url="https://example.com", label="Docs")]),
    dispatchable=False,
)


class RecordingViews(ViewRegistry):
    """Keeps every view the models store, to check which messages they were stored for."""

    def __init__(self) -> None:
        self.stored: list[tuple[ComponentView, int | None]] = []

    @override
    def store(self, view: ComponentView, *, message_id: int | None) -> None:
        self.stored.append((view, message_id))


class World:
    """A bot that has received one guild, with REST calls answered by `transport`."""

    def __init__(self) -> None:
        self.transport = FakeTransport()
        self.rest = make_client(self.transport)
        self.cache = CacheStore(clock=FakeClock())
        self.updater = CacheUpdater(self.cache, intents=Intents(guild_presences=True, guild_members=True))
        self.views = RecordingViews()
        self.state = State(rest=self.rest, cache=self.cache, views=self.views)
        self.state.identify(user_id=BOT, application_id=APPLICATION)

    @classmethod
    async def started(cls) -> Self:
        world = cls()
        await world.dispatch("READY", {
            "v": 10,
            "user": user(BOT, "shoalbot") | {"bot": True},
            "guilds": [{"id": str(GUILD), "unavailable": True}],
            "session_id": "s",
            "resume_gateway_url": "wss://resume.example",
            "application": {"id": str(APPLICATION), "flags": 0},
        })  # fmt: skip
        await world.dispatch("GUILD_CREATE", guild_create())
        return world

    async def dispatch(self, name: str, data: object) -> None:
        await self.updater.apply(DispatchEvent(0, name, None, msgspec.Raw(msgspec.json.encode(data))))

    def guild(self) -> Guild:
        guild = Guild.from_cache(self.state, GUILD)
        assert guild is not None
        return guild

    def requests(self) -> list[tuple[str, str, object]]:
        """Every request so far as `(method, path, JSON body)`."""
        sent: list[tuple[str, str, object]] = []
        for request in self.transport.requests:
            body = msgspec.json.decode(request.body) if request.body else None
            sent.append((request.method, request.url.removeprefix(API), body))
        return sent

    def last_request(self) -> tuple[str, str, object]:
        return self.requests()[-1]

    def last_body(self) -> dict[str, object]:
        """The last request's JSON object body."""
        body = self.requests()[-1][2]
        assert isinstance(body, dict)
        return cast("dict[str, object]", body)
