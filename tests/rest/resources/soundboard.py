from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    CreateSoundboardSoundParams,
    EditSoundboardSoundParams,
    SendSoundboardSoundParams,
)
from tests.support.json_payloads import GUILD_SOUND
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

DEFAULT_SOUND: dict[str, object] = {
    "name": "quack",
    "sound_id": "1",
    "volume": 1.0,
    "emoji_id": None,
    "emoji_name": "\N{DUCK}",
    "available": True,
}
"""Discord's example."""
SOUND = "data:audio/ogg;base64,T2dnUw=="
GUILD_SOUNDS = "/guilds/613425648685547541/soundboard-sounds"

CASES = [
    EndpointCase(
        name="send sound",
        call=lambda client: client.soundboard.send(
            6,
            SendSoundboardSoundParams(
                sound_id=Snowflake(1106714396018884649), source_guild_id=Snowflake(613425648685547541)
            ),
        ),
        method="POST",
        path="/channels/6/send-soundboard-sound",
        body={"sound_id": "1106714396018884649", "source_guild_id": "613425648685547541"},
    ),
    EndpointCase(
        name="list default sounds",
        call=lambda client: client.soundboard.list_default(),
        method="GET",
        path="/soundboard-default-sounds",
        response=[DEFAULT_SOUND],
    ),
    EndpointCase(
        name="list guild sounds",
        call=lambda client: client.soundboard.list(613425648685547541),
        method="GET",
        path=GUILD_SOUNDS,
        response={"items": [GUILD_SOUND]},
        result=[GUILD_SOUND],
    ),
    EndpointCase(
        name="get guild sound",
        call=lambda client: client.soundboard.get(613425648685547541, 1106714396018884649),
        method="GET",
        path=f"{GUILD_SOUNDS}/1106714396018884649",
        response=GUILD_SOUND,
    ),
    EndpointCase(
        name="create guild sound",
        call=lambda client: client.soundboard.create(
            613425648685547541,
            CreateSoundboardSoundParams(name="Yay", sound=SOUND, emoji_id=Snowflake(989193655938064464)),
            reason="new sound",
        ),
        method="POST",
        path=GUILD_SOUNDS,
        body={"name": "Yay", "sound": SOUND, "emoji_id": "989193655938064464"},
        response=GUILD_SOUND,
        reason="new sound",
    ),
    EndpointCase(
        name="modify guild sound",
        call=lambda client: client.soundboard.edit(
            613425648685547541,
            1106714396018884649,
            EditSoundboardSoundParams(volume=0.5, emoji_id=None),
        ),
        method="PATCH",
        path=f"{GUILD_SOUNDS}/1106714396018884649",
        body={"volume": 0.5, "emoji_id": None},
        response=GUILD_SOUND,
    ),
    EndpointCase(
        name="delete guild sound",
        call=lambda client: client.soundboard.delete(613425648685547541, 1106714396018884649),
        method="DELETE",
        path=f"{GUILD_SOUNDS}/1106714396018884649",
    ),
]


@endpoint_cases(CASES)
async def test_soundboard_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
