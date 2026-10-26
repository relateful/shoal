import enum
from typing import Literal

import msgspec
import pytest

from shoal.app_commands.errors import TransformerError
from shoal.app_commands.models import Choice, Range
from shoal.app_commands.parameters import REQUIRED, parameter_from_annotation
from shoal.client.interaction import Interaction
from shoal.core.codec import decode_json, encode_json
from shoal.models.channel import GuildChannel, TextChannel, VoiceChannel
from shoal.models.member import Member
from shoal.models.role import Role
from shoal.models.user import User
from shoal.payloads import ApplicationCommandOptionType as Option
from shoal.payloads.interactions import ResolvedData
from shoal.payloads.message import Attachment
from tests.support.client import started
from tests.support.interactions import command, payload
from tests.support.models import BOB, GENERAL, MODS, VOICE, channel, member, role, user


class Colour(enum.Enum):
    RED = "red"
    BLUE = "blue"


def option(annotation: object, default: object = REQUIRED) -> dict[str, object]:
    built = parameter_from_annotation("value", annotation, default).to_option()
    return msgspec.json.decode(encode_json(built), type=dict[str, object])


@pytest.mark.parametrize(
    ("annotation", "kind"),
    [(str, Option.STRING), (int, Option.INTEGER), (float, Option.NUMBER), (bool, Option.BOOLEAN)],
)
def test_primitives_become_their_option_types(annotation: type, kind: Option) -> None:
    assert option(annotation) == {
        "type": kind,
        "name": "value",
        "description": "No description given",
        "required": True,
    }


def test_optional_parameters_are_not_required() -> None:
    parameter = parameter_from_annotation("reason", str | None, REQUIRED)
    assert parameter.default is None
    assert not parameter.required
    assert "required" not in option(int, 3)


def test_ranges_bound_values_and_string_lengths() -> None:
    assert option(Range[int, 0, 7]) == option(int) | {"min_value": 0, "max_value": 7}
    assert option(Range[float, 0.5, None])["min_value"] == 0.5
    assert {key: value for key, value in option(Range[str, 1, 100]).items() if "length" in key} == {
        "min_length": 1,
        "max_length": 100,
    }


def test_literals_and_enums_become_choices() -> None:
    assert option(Literal["a", "b"])["choices"] == [{"name": "a", "value": "a"}, {"name": "b", "value": "b"}]
    assert option(Literal[1, 2])["type"] == Option.INTEGER
    assert option(Colour)["choices"] == [{"name": "RED", "value": "red"}, {"name": "BLUE", "value": "blue"}]
    with pytest.raises(TypeError, match="values of one type"):
        option(Literal["a", 1])
    with pytest.raises(TypeError, match="cannot be a choice"):
        option(Literal[True, False])
    with pytest.raises(TypeError, match="cannot be a choice"):
        option(Literal[b"raw"])


def test_choice_parameters_receive_the_choice_picked() -> None:
    parameter = parameter_from_annotation("colour", Choice[str], REQUIRED)
    parameter.choices = [Choice(name="Red", value="red")]
    assert parameter.type is Option.STRING


def test_users_roles_and_mentionables() -> None:
    assert option(Member)["type"] == Option.USER
    assert option(Member | User)["type"] == Option.USER
    assert option(Role)["type"] == Option.ROLE
    assert option(Member | Role)["type"] == Option.MENTIONABLE
    assert option(Attachment)["type"] == Option.ATTACHMENT


def test_channels_limit_the_channel_types_offered() -> None:
    assert option(TextChannel | VoiceChannel)["channel_types"] == [0, 5, 2]
    assert "channel_types" not in option(GuildChannel)


def test_unsupported_annotations_are_refused() -> None:
    with pytest.raises(TypeError, match="cannot be a command option"):
        option(list[int])
    with pytest.raises(TypeError, match="both a channel and a user"):
        option(TextChannel | Member)


async def test_primitive_values_are_converted() -> None:
    client, _ = await started()
    interaction = await client.process_interaction(payload(command("x")))
    number = parameter_from_annotation("n", float, REQUIRED)
    assert number.convert(interaction, 3, None) == 3.0
    colour = parameter_from_annotation("c", Colour, REQUIRED)
    assert colour.convert(interaction, "blue", None) is Colour.BLUE
    with pytest.raises(TransformerError, match="not a Colour"):
        colour.convert(interaction, "green", None)
    picked = parameter_from_annotation("p", Choice[str], REQUIRED)
    picked.choices = [Choice(name="Red", value="red")]
    assert picked.convert(interaction, "red", None) == Choice(name="Red", value="red")
    with pytest.raises(TransformerError, match="not one of the choices"):
        picked.convert(interaction, "blue", None)


async def test_ids_without_resolved_data_are_refused() -> None:
    client, _ = await started()
    interaction = await client.process_interaction(payload(command("x")))
    for annotation in (Member, Role, Attachment):
        with pytest.raises(TransformerError, match="was not sent"):
            parameter_from_annotation("v", annotation, REQUIRED).convert(interaction, "99", None)


async def converting() -> Interaction:
    """A command interaction in the test guild, for converting values with."""
    client, _ = await started()
    return await client.process_interaction(payload(command("x")))


def resolved(**fields: object) -> ResolvedData:
    return decode_json(encode_json(fields), ResolvedData)


BOB_USER = {str(BOB): user(BOB, "bob")}
BOB_MEMBER = {str(BOB): {key: value for key, value in member(BOB, "bob").items() if key != "user"}}


async def test_users_become_members_in_the_guild_and_users_elsewhere() -> None:
    interaction = await converting()
    as_member = parameter_from_annotation("who", Member, REQUIRED)
    either = parameter_from_annotation("who", Member | User, REQUIRED)
    sent = resolved(users=BOB_USER, members=BOB_MEMBER)
    assert isinstance(as_member.convert(interaction, str(BOB), sent), Member)
    left_server = resolved(users=BOB_USER)
    assert isinstance(either.convert(interaction, str(BOB), left_server), User)
    with pytest.raises(TransformerError, match="not a member of this server"):
        as_member.convert(interaction, str(BOB), left_server)


async def test_mentionables_are_a_role_or_a_user() -> None:
    interaction = await converting()
    mentionable = parameter_from_annotation("target", Member | Role, REQUIRED)
    sent = resolved(users=BOB_USER, members=BOB_MEMBER, roles={str(MODS): role(MODS, "mods", position=2)})
    picked_role = mentionable.convert(interaction, str(MODS), sent)
    assert isinstance(picked_role, Role)
    assert picked_role.id == MODS
    assert isinstance(mentionable.convert(interaction, str(BOB), sent), Member)


async def test_roles_need_a_guild() -> None:
    client, _ = await started()
    in_dm = await client.process_interaction(payload(command("x", in_guild=False)))
    sent = resolved(roles={str(MODS): role(MODS, "mods", position=2)})
    with pytest.raises(TransformerError, match="role was not sent"):
        parameter_from_annotation("r", Role, REQUIRED).convert(in_dm, str(MODS), sent)


async def test_channels_come_from_the_cache_or_the_resolved_data() -> None:
    interaction = await converting()
    text = parameter_from_annotation("where", TextChannel, REQUIRED)
    cached = text.convert(interaction, str(GENERAL), None)
    assert isinstance(cached, TextChannel)
    assert cached.id == GENERAL
    with pytest.raises(TransformerError, match="not a TextChannel"):
        text.convert(interaction, str(VOICE), None)
    unknown = 999
    sent = resolved(channels={str(unknown): channel(unknown, 0, "new", permissions="0")})
    assert isinstance(text.convert(interaction, str(unknown), sent), TextChannel)
    with pytest.raises(TransformerError, match="channel was not sent"):
        text.convert(interaction, "998", sent)


async def test_attachments_come_from_the_resolved_data() -> None:
    interaction = await converting()
    attachment = {
        "id": "55",
        "filename": "a.png",
        "size": 10,
        "url": "https://cdn.example/a.png",
        "proxy_url": "https://media.example/a.png",
    }
    found = parameter_from_annotation("file", Attachment, REQUIRED).convert(
        interaction, "55", resolved(attachments={"55": attachment})
    )
    assert isinstance(found, Attachment)
    assert found.filename == "a.png"
