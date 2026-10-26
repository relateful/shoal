from datetime import UTC, datetime

from shoal.core.snowflake import Snowflake
from shoal.payloads import EditCurrentVoiceStateParams, EditVoiceStateParams
from tests.support.json_payloads import REGION
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

VOICE_STATE: dict[str, object] = {
    "guild_id": "2",
    "channel_id": "6",
    "user_id": "1",
    "session_id": "abc",
    "deaf": False,
    "mute": False,
    "self_deaf": False,
    "self_mute": True,
    "self_video": False,
    "suppress": True,
    "request_to_speak_timestamp": None,
}

CASES = [
    EndpointCase(
        name="list regions",
        call=lambda client: client.voice.list_regions(),
        method="GET",
        path="/voice/regions",
        response=[REGION],
    ),
    EndpointCase(
        name="get own voice state",
        call=lambda client: client.voice_states.get_me(2),
        method="GET",
        path="/guilds/2/voice-states/@me",
        response=VOICE_STATE,
    ),
    EndpointCase(
        name="get user voice state",
        call=lambda client: client.voice_states.get(2, 1),
        method="GET",
        path="/guilds/2/voice-states/1",
        response=VOICE_STATE,
    ),
    EndpointCase(
        name="request to speak",
        call=lambda client: client.voice_states.edit_me(
            2,
            EditCurrentVoiceStateParams(
                channel_id=Snowflake(6), request_to_speak_timestamp=datetime(2026, 1, 1, tzinfo=UTC)
            ),
        ),
        method="PATCH",
        path="/guilds/2/voice-states/@me",
        body={"channel_id": "6", "request_to_speak_timestamp": "2026-01-01T00:00:00Z"},
    ),
    EndpointCase(
        name="unsuppress a user",
        call=lambda client: client.voice_states.edit(
            2, 1, EditVoiceStateParams(channel_id=Snowflake(6), suppress=False)
        ),
        method="PATCH",
        path="/guilds/2/voice-states/1",
        body={"channel_id": "6", "suppress": False},
    ),
]


@endpoint_cases(CASES)
async def test_voice_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
