import pytest

from shoal.core.snowflake import Snowflake
from shoal.models.base import Object
from shoal.models.emoji import AppEmoji, Emoji, partial_emoji
from shoal.payloads import Emoji as EmojiPayload
from shoal.payloads import PartialEmoji
from tests.support.models import APPLICATION, EMOJI, GUILD, MODS, World, decoded, user


def payload(data: object) -> EmojiPayload:
    return decoded(data, EmojiPayload)


async def test_emojis_render_as_message_text() -> None:
    world = await World.started()
    wave = world.guild().get_emoji(EMOJI)
    assert wave is not None
    assert str(wave) == f"<:wave:{EMOJI}>"
    animated = Emoji(world.state, payload({"id": "5", "name": "dance", "animated": True}), GUILD)
    assert str(animated) == "<a:dance:5>"
    assert animated.url == "https://cdn.discordapp.com/emojis/5.webp?animated=true"
    assert wave.url == f"https://cdn.discordapp.com/emojis/{EMOJI}.webp"


async def test_emojis_read_their_payload_and_the_cache() -> None:
    world = await World.started()
    wave = Emoji.from_cache(world.state, EMOJI)
    assert wave is not None
    assert (wave.name, wave.animated, wave.managed, wave.available, wave.require_colons) == (
        "wave",
        False,
        False,
        True,
        True,
    )
    assert [role.id for role in wave.roles] == [MODS]
    assert wave.guild is not None
    assert wave.guild_id == GUILD
    assert wave.user is None
    assert Emoji.from_cache(world.state, 999) is None
    uploaded = Emoji(world.state, payload({"id": "5", "name": "x", "user": user(3, "alice")}), GUILD)
    assert uploaded.user is not None
    assert uploaded.user.name == "alice"
    assert repr(uploaded) == "<Emoji id=5 name='x' animated=False>"


async def test_a_unicode_emoji_is_not_a_custom_emoji() -> None:
    world = World()
    with pytest.raises(ValueError, match="unicode"):
        Emoji(world.state, payload({"id": None, "name": "\N{FIRE}"}), GUILD)


async def test_edit_and_delete() -> None:
    world = await World.started()
    wave = world.guild().get_emoji(EMOJI)
    assert wave is not None
    world.transport.queue(200, {"id": str(EMOJI), "name": "hello"})
    edited = await wave.edit(name="hello", roles=None)
    assert world.last_request() == (
        "PATCH",
        f"/guilds/{GUILD}/emojis/{EMOJI}",
        {"name": "hello", "roles": None},
    )
    assert edited.name == "hello"
    world.transport.queue(200, {"id": str(EMOJI), "name": "hello"})
    await wave.edit(roles=[Object(MODS)])
    assert world.last_request()[2] == {"roles": [str(MODS)]}
    world.transport.queue(204)
    await wave.delete(reason="old")
    assert world.last_request()[:2] == ("DELETE", f"/guilds/{GUILD}/emojis/{EMOJI}")


async def test_application_emojis_render_and_change() -> None:
    world = World()
    star = AppEmoji(world.state, payload({"id": "9", "name": "star", "animated": True}), APPLICATION)
    assert (str(star), star.name, star.application_id, star.animated) == (
        "<a:star:9>",
        "star",
        APPLICATION,
        True,
    )
    assert star.payload.name == "star"
    assert star.url == "https://cdn.discordapp.com/emojis/9.webp?animated=true"
    assert repr(star) == "<AppEmoji id=9 name='star' animated=True>"
    world.transport.queue(200, {"id": "9", "name": "shine"})
    renamed = await star.edit(name="shine")
    assert world.last_request() == ("PATCH", f"/applications/{APPLICATION}/emojis/9", {"name": "shine"})
    assert renamed.name == "shine"
    world.transport.queue(204)
    await star.delete()
    assert world.last_request()[:2] == ("DELETE", f"/applications/{APPLICATION}/emojis/9")
    with pytest.raises(ValueError, match="an ID and a name"):
        AppEmoji(world.state, payload({"id": None, "name": "\N{FIRE}"}), APPLICATION)


async def test_every_kind_of_emoji_becomes_a_partial_emoji() -> None:
    world = await World.started()
    wave = world.guild().get_emoji(EMOJI)
    assert wave is not None
    star = AppEmoji(world.state, payload({"id": "9", "name": "star"}), APPLICATION)
    assert partial_emoji("\N{FIRE}") == PartialEmoji(name="\N{FIRE}")
    assert partial_emoji(wave) == PartialEmoji(id=Snowflake(EMOJI), name="wave", animated=False)
    assert partial_emoji(star) == PartialEmoji(id=Snowflake(9), name="star", animated=False)
    given = PartialEmoji(id=Snowflake(1), name="x")
    assert partial_emoji(given) is given
