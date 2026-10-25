"""Interactions: what a user did with an app, and how the app answers.

Discord: https://docs.discord.com/developers/interactions/receiving-and-responding
"""

from shoal.core.enums import DiscordIntEnum


class InteractionContextType(DiscordIntEnum):
    """Where an interaction can be used, or where it happened.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-context-types
    """

    GUILD = 0
    BOT_DM = 1
    PRIVATE_CHANNEL = 2
