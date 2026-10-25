"""Applications: where an app can be installed, and where its interactions can be used.

Discord: https://docs.discord.com/developers/resources/application

Not yet modeled: the application object itself and its endpoints. Decoding ignores those keys until
they are added.
"""

from shoal.core.enums import DiscordIntEnum


class ApplicationIntegrationType(DiscordIntEnum):
    """Where an app is installed: to a server, or to a user's account.

    Discord: https://docs.discord.com/developers/resources/application#application-object-application-integration-types
    """

    GUILD_INSTALL = 0
    USER_INSTALL = 1


class InteractionContextType(DiscordIntEnum):
    """Where an interaction can be used, or where it happened.

    Discord: https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-object-interaction-context-types
    """

    GUILD = 0
    BOT_DM = 1
    PRIVATE_CHANNEL = 2
