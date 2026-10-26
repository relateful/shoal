from shoal.models.activity import Competing, CustomActivity, Game, Listening, Streaming, Watching
from shoal.payloads import ActivityType, BotActivity


def test_activities_are_built_like_discord_py() -> None:
    assert Game("chess") == BotActivity(name="chess", type=ActivityType.PLAYING)
    assert Streaming("live", url="https://twitch.tv/x") == BotActivity(
        name="live", type=ActivityType.STREAMING, url="https://twitch.tv/x"
    )
    assert Listening("rain").type is ActivityType.LISTENING
    assert Watching("tide").type is ActivityType.WATCHING
    assert Competing("cup").type is ActivityType.COMPETING
    assert CustomActivity("Fishing") == BotActivity(
        name="Custom Status", type=ActivityType.CUSTOM, state="Fishing"
    )
