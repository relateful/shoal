import logging
from pathlib import Path

import pytest

from shoal.client.client import Client
from shoal.emojis.registry import AppEmojis, DeclaredEmoji, EmojisNotLoadedError, app_emoji
from shoal.models.emoji import AppEmoji
from tests.support.client import INTENTS, logged_in
from tests.support.fakes import FakeTransport
from tests.support.models import APPLICATION

PNG = b"\x89PNG\r\n\x1a\n"


class Icons(AppEmojis):
    approve = app_emoji("\N{WHITE HEAVY CHECK MARK}")
    deny = app_emoji("\N{CROSS MARK}")
    star = app_emoji()


async def loaded(registry: AppEmojis | None = None, *emojis: tuple[int, str]) -> tuple[Client, FakeTransport]:
    """A logged-in client whose application has `emojis`, loaded into `registry`."""
    client, transport = await logged_in()
    if registry is not None:
        transport.queue(200, {"items": [{"id": str(emoji_id), "name": name} for emoji_id, name in emojis]})
        await registry.load(client.state, APPLICATION)
    return client, transport


async def test_emojis_are_found_by_name_and_attribute() -> None:
    registry = AppEmojis()
    await loaded(registry, (1, "approve"), (2, "star"))
    approve = registry["approve"]
    assert isinstance(approve, AppEmoji)
    assert registry.get("approve") is approve
    assert registry.approve is approve
    assert registry.resolve("approve") is approve
    assert registry.text("star") == "<:star:2>"
    assert "star" in registry
    assert "missing" not in registry
    assert [emoji.name for emoji in registry] == ["approve", "star"]
    assert len(registry) == 2
    assert registry.get("missing") is None


async def test_missing_names_use_their_fallback_or_raise(caplog: pytest.LogCaptureFixture) -> None:
    registry = AppEmojis(fallbacks={"ok": "\N{OK HAND SIGN}"})
    await loaded(registry)
    with caplog.at_level(logging.WARNING, logger="shoal.emojis"):
        assert registry.text("ok") == "\N{OK HAND SIGN}"
        assert registry.ok == "\N{OK HAND SIGN}"
    assert caplog.text.count("'ok' is not uploaded") == 1
    with pytest.raises(KeyError, match="upload it, or give it a fallback"):
        registry.resolve("nope")
    with pytest.raises(AttributeError, match="no emoji named 'nope'"):
        _ = registry.nope
    with pytest.raises(AttributeError):
        _ = registry._private
    with pytest.raises(KeyError, match="no emoji named"):
        _ = registry["nope"]


async def test_declared_emojis_carry_their_fallbacks(caplog: pytest.LogCaptureFixture) -> None:
    icons = Icons(fallbacks={"extra": "+"})
    assert isinstance(Icons.approve, DeclaredEmoji)
    assert set(Icons.declared) == {"approve", "deny", "star"}
    assert icons.fallbacks == {
        "approve": "\N{WHITE HEAVY CHECK MARK}",
        "deny": "\N{CROSS MARK}",
        "extra": "+",
    }
    with caplog.at_level(logging.WARNING, logger="shoal.emojis"):
        await loaded(icons, (1, "approve"))
    assert "declared application emojis not uploaded: deny, star" in caplog.text
    assert icons.missing == ["deny", "star"]
    assert str(icons.approve) == "<:approve:1>"
    assert icons.deny == "\N{CROSS MARK}"
    with pytest.raises(KeyError):
        _ = icons.star


def test_declared_names_cannot_hide_the_registry() -> None:
    # Type checkers already refuse this; the check is for code they do not see.
    with pytest.raises(TypeError, match="declares get, sync"):
        type("Clashing", (AppEmojis,), {"sync": app_emoji(), "get": app_emoji()})


async def test_the_client_loads_its_registry_at_login() -> None:
    icons = Icons()
    client = Client(intents=INTENTS, app_emojis=icons)
    assert client.app_emojis is icons
    default, _ = await logged_in()
    assert len(default.app_emojis) == 0


async def test_emojis_are_created_deleted_and_synced() -> None:
    registry = AppEmojis()
    _, transport = await loaded(registry)
    transport.queue(200, {"id": "5", "name": "new"})
    created = await registry.create("new", PNG)
    assert registry["new"] is created
    transport.queue(204)
    await registry.delete("new")
    assert "new" not in registry
    with pytest.raises(KeyError):
        await registry.delete("new")


async def test_a_sync_from_the_registry_fetches_the_emojis_again(tmp_path: Path) -> None:
    (tmp_path / "wave.png").write_bytes(PNG)
    registry = AppEmojis()
    _, transport = await loaded(registry)
    transport.queue(200, {"items": []})
    transport.queue(200, {"id": "6", "name": "wave"})
    transport.queue(200, {"items": [{"id": "6", "name": "wave"}]})
    report = await registry.sync(tmp_path)
    assert report.created == ["wave"]
    assert registry.text("wave") == "<:wave:6>"
    transport.queue(200, {"items": [{"id": "6", "name": "wave"}]})
    dry = await registry.sync(tmp_path, dry_run=True)
    assert dry.unchanged == ["wave"]


async def test_a_registry_needs_the_client_to_have_logged_in(tmp_path: Path) -> None:
    registry = AppEmojis()
    with pytest.raises(EmojisNotLoadedError, match="logs in"):
        await registry.refresh()
    with pytest.raises(EmojisNotLoadedError):
        await registry.create("x", PNG)
    with pytest.raises(EmojisNotLoadedError):
        await registry.sync(tmp_path)
