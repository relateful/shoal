from pathlib import Path

import pytest

import shoal.emojis.__main__ as command
from shoal.rest.client import RestClient, Token
from tests.support.fakes import FakeTransport
from tests.support.json_payloads import APPLICATION
from tests.support.rest import make_client

PNG = b"\x89PNG\r\n\x1a\n"


def patched(monkeypatch: pytest.MonkeyPatch, transport: FakeTransport) -> list[Token]:
    """Point the command at `transport`; returns the tokens it was given."""
    tokens: list[Token] = []

    def rest(token: Token) -> RestClient:
        tokens.append(token)
        return make_client(transport, token=token)

    monkeypatch.setattr(command, "RestClient", rest)
    return tokens


def test_the_token_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exited:
        command.main(["sync", str(tmp_path)])
    assert exited.value.code == 2


def test_a_sync_prints_its_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "wave.png").write_bytes(PNG)
    monkeypatch.setenv("BOT_TOKEN", "secret-token")
    transport = FakeTransport()
    transport.queue(200, APPLICATION)
    transport.queue(200, {"items": []})
    tokens = patched(monkeypatch, transport)
    status = command.main(["sync", str(tmp_path), "--dry-run", "--token-env", "BOT_TOKEN"])
    assert status == 0
    assert capsys.readouterr().out == "would sync (dry run): 1 created\n"
    assert tokens == [Token.bot("secret-token")]


def test_a_failed_emoji_fails_the_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "bitmap.png").write_bytes(b"BM")
    monkeypatch.setenv("DISCORD_TOKEN", "secret-token")
    transport = FakeTransport()
    transport.queue(200, APPLICATION)
    transport.queue(200, {"items": []})
    patched(monkeypatch, transport)
    assert command.main(["sync", str(tmp_path), "--manifest", str(tmp_path / "lock.json")]) == 1
