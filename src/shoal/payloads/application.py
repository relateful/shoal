"""Applications: where an app can be installed.

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
