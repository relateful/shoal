"""The endpoints `RestClient` is assembled from, one class per Discord resource.

Use them through `RestClient`; they are separate only to keep each resource's methods together.

Discord: https://docs.discord.com/developers/reference#http-api
"""

from shoal.rest.resources.application_commands import ApplicationCommandEndpoints
from shoal.rest.resources.audit_log import AuditLogEndpoints
from shoal.rest.resources.auto_moderation import AutoModerationEndpoints
from shoal.rest.resources.channel import ChannelEndpoints
from shoal.rest.resources.emoji import EmojiEndpoints
from shoal.rest.resources.gateway import GatewayEndpoints
from shoal.rest.resources.guild import GuildEndpoints
from shoal.rest.resources.guild_template import GuildTemplateEndpoints
from shoal.rest.resources.interactions import InteractionEndpoints
from shoal.rest.resources.invite import InviteEndpoints
from shoal.rest.resources.message import MessageEndpoints
from shoal.rest.resources.scheduled_event import ScheduledEventEndpoints
from shoal.rest.resources.soundboard import SoundboardEndpoints
from shoal.rest.resources.stage_instance import StageInstanceEndpoints
from shoal.rest.resources.sticker import StickerEndpoints
from shoal.rest.resources.user import UserEndpoints
from shoal.rest.resources.voice import VoiceEndpoints
from shoal.rest.resources.webhook import WebhookEndpoints

__all__ = [
    "ApplicationCommandEndpoints",
    "AuditLogEndpoints",
    "AutoModerationEndpoints",
    "ChannelEndpoints",
    "EmojiEndpoints",
    "GatewayEndpoints",
    "GuildEndpoints",
    "GuildTemplateEndpoints",
    "InteractionEndpoints",
    "InviteEndpoints",
    "MessageEndpoints",
    "ScheduledEventEndpoints",
    "SoundboardEndpoints",
    "StageInstanceEndpoints",
    "StickerEndpoints",
    "UserEndpoints",
    "VoiceEndpoints",
    "WebhookEndpoints",
]
