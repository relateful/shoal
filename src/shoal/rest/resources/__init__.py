"""The endpoints of `RestClient`, one class per resource.

Each is reached as an attribute of the client: `rest.messages`, `rest.members`.

Discord: https://docs.discord.com/developers/reference#http-api
"""

from shoal.rest.resources.application import Applications, OAuth2, RoleConnections
from shoal.rest.resources.application_commands import Commands
from shoal.rest.resources.application_identity import Identities
from shoal.rest.resources.audit_log import AuditLogs
from shoal.rest.resources.auto_moderation import AutoMod
from shoal.rest.resources.channel import Channels, Threads
from shoal.rest.resources.emoji import Emojis
from shoal.rest.resources.gateway import Gateway
from shoal.rest.resources.guild import Guilds, Members, Roles
from shoal.rest.resources.guild_template import Templates
from shoal.rest.resources.interactions import Interactions
from shoal.rest.resources.invite import Invites
from shoal.rest.resources.lobby import Lobbies
from shoal.rest.resources.message import Messages, Polls, Reactions
from shoal.rest.resources.monetization import Entitlements, SKUs, Subscriptions
from shoal.rest.resources.scheduled_event import ScheduledEvents
from shoal.rest.resources.soundboard import Soundboard
from shoal.rest.resources.stage_instance import StageInstances
from shoal.rest.resources.sticker import Stickers
from shoal.rest.resources.user import Users
from shoal.rest.resources.voice import Voice, VoiceStates
from shoal.rest.resources.webhook import Webhooks

__all__ = [
    "Applications",
    "AuditLogs",
    "AutoMod",
    "Channels",
    "Commands",
    "Emojis",
    "Entitlements",
    "Gateway",
    "Guilds",
    "Identities",
    "Interactions",
    "Invites",
    "Lobbies",
    "Members",
    "Messages",
    "OAuth2",
    "Polls",
    "Reactions",
    "RoleConnections",
    "Roles",
    "SKUs",
    "ScheduledEvents",
    "Soundboard",
    "StageInstances",
    "Stickers",
    "Subscriptions",
    "Templates",
    "Threads",
    "Users",
    "Voice",
    "VoiceStates",
    "Webhooks",
]
