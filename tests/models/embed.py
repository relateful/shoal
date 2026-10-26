from datetime import UTC, datetime

import pytest

from shoal.core.codec import PayloadDecodeError
from shoal.models.embed import Embed
from shoal.payloads import EmbedField


def test_builds_like_discord_py() -> None:
    moment = datetime(2024, 1, 1, tzinfo=UTC)
    embed = (
        Embed(
            title="Stats", description="Today", url="https://example.com", colour=0x5865F2, timestamp=moment
        )
        .set_author(name="Shoal", icon_url="https://example.com/a.png")
        .set_footer(text="hourly")
        .set_image(url="https://example.com/i.png")
        .set_thumbnail(url="https://example.com/t.png")
        .add_field(name="Members", value="1,024")
        .add_field(name="Online", value="12", inline=False)
    )
    assert embed.to_dict() == {
        "title": "Stats",
        "description": "Today",
        "url": "https://example.com",
        "timestamp": "2024-01-01T00:00:00Z",
        "color": 0x5865F2,
        "footer": {"text": "hourly"},
        "image": {"url": "https://example.com/i.png"},
        "thumbnail": {"url": "https://example.com/t.png"},
        "author": {"name": "Shoal", "icon_url": "https://example.com/a.png"},
        "fields": [
            {"name": "Members", "value": "1,024", "inline": True},
            {"name": "Online", "value": "12", "inline": False},
        ],
    }


def test_color_and_colour_are_the_same() -> None:
    embed = Embed(color=0xFF0000)
    assert embed.colour == embed.color == 0xFF0000
    embed.colour = 0x00FF00
    assert embed.color == 0x00FF00
    embed.colour = None
    assert embed.to_dict() == {}


def test_attributes_can_be_set_and_cleared() -> None:
    embed = Embed()
    embed.title, embed.description, embed.url = "t", "d", "https://example.com"
    embed.timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    assert (embed.title, embed.description, embed.url) == ("t", "d", "https://example.com")
    embed.title = embed.description = embed.url = None
    embed.timestamp = None
    assert embed.to_dict() == {}


def test_fields_can_be_inserted_replaced_and_removed() -> None:
    embed = Embed().add_field(name="a", value="1").add_field(name="c", value="3")
    embed.insert_field_at(1, name="b", value="2")
    assert [field.name for field in embed.fields] == ["a", "b", "c"]
    embed.set_field_at(0, name="A", value="1", inline=False)
    assert embed.fields[0] == EmbedField(name="A", value="1", inline=False)
    embed.remove_field(1).remove_field(10)
    assert [field.name for field in embed.fields] == ["A", "c"]
    with pytest.raises(IndexError):
        embed.set_field_at(5, name="x", value="y")
    embed.clear_fields()
    assert embed.fields == []
    assert "fields" not in embed.to_dict()


def test_parts_can_be_removed() -> None:
    embed = Embed().set_footer(text="f").set_author(name="a").set_image(url="i").set_thumbnail(url="t")
    embed.remove_footer().remove_author().set_image(url=None).set_thumbnail(url=None)
    assert embed.to_dict() == {}
    assert embed.footer is None
    assert embed.author is None
    assert embed.image is None
    assert embed.thumbnail is None


def test_received_embeds_round_trip() -> None:
    data = {"title": "t", "type": "rich", "provider": {"name": "YouTube"}, "video": {"url": "v"}}
    embed = Embed.from_dict(data)
    assert embed.to_dict() == data
    assert embed.provider is not None
    assert embed.video is not None
    assert Embed.from_payload(embed.to_payload()).to_dict() == data
    with pytest.raises(PayloadDecodeError):
        Embed.from_dict({"title": 5})


def test_length_counts_what_discord_limits() -> None:
    embed = Embed(title="ab", description="cde").add_field(name="f", value="gh")
    embed.set_footer(text="ij").set_author(name="k")
    assert len(embed) == 11
    assert repr(embed) == "<Embed title='ab' fields=1>"
