"""The bot's activity: `Game("chess")`, `Streaming(...)`, `CustomActivity(...)`.

    client = Client(intents=intents, activity=Game("with fish"))
    await client.change_presence(activity=Watching("the tide"))

Each returns the `BotActivity` payload the gateway takes; bots may only set a name, a type, a stream
URL and a custom status.

Discord: https://docs.discord.com/developers/events/gateway-events#activity-object
"""

from shoal.payloads.gateway_events import ActivityType, BotActivity


def Game(name: str, /) -> BotActivity:  # noqa: N802 - reads as the class of activity it builds
    """Shows "Playing `name`"."""
    return BotActivity(name=name, type=ActivityType.PLAYING)


def Streaming(name: str, /, *, url: str) -> BotActivity:  # noqa: N802 - reads as the class of activity it builds
    """Shows "Streaming `name`", linking to a Twitch or YouTube `url`."""
    return BotActivity(name=name, type=ActivityType.STREAMING, url=url)


def Listening(name: str, /) -> BotActivity:  # noqa: N802 - the same style as Game
    """Shows "Listening to `name`"."""
    return BotActivity(name=name, type=ActivityType.LISTENING)


def Watching(name: str, /) -> BotActivity:  # noqa: N802 - the same style as Game
    """Shows "Watching `name`"."""
    return BotActivity(name=name, type=ActivityType.WATCHING)


def Competing(name: str, /) -> BotActivity:  # noqa: N802 - the same style as Game
    """Shows "Competing in `name`"."""
    return BotActivity(name=name, type=ActivityType.COMPETING)


def CustomActivity(state: str, /) -> BotActivity:  # noqa: N802 - reads as the class of activity it builds
    """A custom status: the text shown under the bot's name."""
    return BotActivity(name="Custom Status", type=ActivityType.CUSTOM, state=state)
