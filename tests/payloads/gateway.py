import pytest

from shoal.payloads import (
    GatewayCloseCode,
    GatewayOpcode,
    Intents,
)


def test_intents_default_excludes_privileged() -> None:
    default = Intents.default()
    assert not default.is_privileged
    assert default.guilds
    assert not default.message_content
    assert Intents.privileged().is_privileged
    assert Intents.all() == default | Intents.privileged()


@pytest.mark.parametrize(
    ("code", "reconnect", "new_session"),
    [
        (GatewayCloseCode.UNKNOWN_ERROR, True, False),
        (GatewayCloseCode.INVALID_SEQ, True, True),
        (GatewayCloseCode.SESSION_TIMED_OUT, True, True),
        (GatewayCloseCode.AUTHENTICATION_FAILED, False, False),
        (GatewayCloseCode.DISALLOWED_INTENTS, False, False),
        (GatewayCloseCode(4999), True, False),
    ],
)
def test_close_code_rules_follow_the_docs_table(
    code: GatewayCloseCode, *, reconnect: bool, new_session: bool
) -> None:
    assert code.can_reconnect is reconnect
    assert code.invalidates_session is new_session


def test_gateway_code_range() -> None:
    assert GatewayCloseCode.is_gateway_code(4000)
    assert GatewayCloseCode.is_gateway_code(4999)
    assert not GatewayCloseCode.is_gateway_code(1000)
    assert not GatewayCloseCode.is_gateway_code(5000)


def test_only_app_commands_are_commands() -> None:
    assert GatewayOpcode.PRESENCE_UPDATE.is_command
    assert GatewayOpcode.REQUEST_GUILD_MEMBERS.is_command
    assert not GatewayOpcode.IDENTIFY.is_command
    assert not GatewayOpcode.HEARTBEAT.is_command
