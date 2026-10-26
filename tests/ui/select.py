import asyncio

import msgspec

from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.core.snowflake import Snowflake
from shoal.models.channel import TextChannel
from shoal.models.member import Member
from shoal.models.role import Role
from shoal.models.user import User
from shoal.payloads import ChannelType, SelectDefaultValue, SelectDefaultValueType, SelectOption
from shoal.ui.select import ChannelSelect, MentionableSelect, RoleSelect, Select, UserSelect, select
from shoal.ui.view import View
from tests.support.client import started
from tests.support.interactions import common, payload
from tests.support.models import ALICE, BOB, GENERAL, MODS, channel, member, role, user

type Json = dict[str, object]


def json(value: object) -> object:
    return msgspec.json.decode(encode_json(value))


def chosen(custom_id: str, kind: int, values: list[str], resolved: Json) -> Json:
    data: Json = {"custom_id": custom_id, "component_type": kind, "values": values, "resolved": resolved}
    return common() | {"type": 3, "data": data}


def test_string_selects_render_their_options() -> None:
    picker = Select(
        custom_id="pick", placeholder="Pick", min_values=0, max_values=2, required=False, disabled=True
    )
    picker.add_option(label="Red", emoji="\N{LARGE RED CIRCLE}", default=True)
    picker.add_option(label="Blue", value="b", description="the blue one")
    assert json(picker.to_component()) == {
        "type": 3,
        "custom_id": "pick",
        "options": [
            {"label": "Red", "value": "Red", "emoji": {"name": "\N{LARGE RED CIRCLE}"}, "default": True},
            {"label": "Blue", "value": "b", "description": "the blue one"},
        ],
        "placeholder": "Pick",
        "min_values": 0,
        "max_values": 2,
        "required": False,
        "disabled": True,
    }
    assert picker.values == []
    assert Select(options=[SelectOption(label="a", value="a")]).options[0].value == "a"


def test_resolved_selects_render() -> None:
    default = SelectDefaultValue(id=Snowflake(1), type=SelectDefaultValueType.USER)
    assert json(UserSelect(custom_id="u", default_values=[default]).to_component()) == {
        "type": 5,
        "custom_id": "u",
        "default_values": [{"id": "1", "type": "user"}],
        "min_values": 1,
        "max_values": 1,
    }
    assert json(RoleSelect(custom_id="r").to_component()) == {
        "type": 6,
        "custom_id": "r",
        "min_values": 1,
        "max_values": 1,
    }
    assert json(MentionableSelect(custom_id="m", placeholder="Who?").to_component()) == {
        "type": 7,
        "custom_id": "m",
        "placeholder": "Who?",
        "min_values": 1,
        "max_values": 1,
    }
    channels = ChannelSelect(custom_id="c", channel_types=[ChannelType.GUILD_TEXT])
    assert json(channels.to_component()) == {
        "type": 8,
        "custom_id": "c",
        "channel_types": [0],
        "min_values": 1,
        "max_values": 1,
    }


async def test_choices_resolve_into_models() -> None:
    client, _ = await started()
    users = UserSelect(custom_id="u")
    roles = RoleSelect(custom_id="r")
    mentionables = MentionableSelect(custom_id="m")
    channels = ChannelSelect(custom_id="c")
    view = View(timeout=None)
    for item in (users, roles, mentionables, channels):
        view.add_item(item)
    client.add_view(view)
    alice = member(ALICE, "alice")
    partial = {key: value for key, value in alice.items() if key not in {"user", "deaf", "mute"}}
    resolved: Json = {
        "users": {str(ALICE): user(ALICE, "alice"), str(BOB): user(BOB, "bob")},
        "members": {str(ALICE): partial},
        "roles": {str(MODS): role(MODS, "mods", position=2)},
        "channels": {str(GENERAL): channel(GENERAL, 0, "general")},
    }
    await client.process_interaction(payload(chosen("u", 5, [str(ALICE), str(BOB), "999"], resolved)))
    await client.process_interaction(payload(chosen("r", 6, [str(MODS)], resolved)))
    await client.process_interaction(payload(chosen("m", 7, [str(BOB), str(MODS)], resolved)))
    await client.process_interaction(payload(chosen("c", 8, [str(GENERAL)], resolved)))
    assert [type(found) for found in users.values] == [Member, User]
    assert [found.id for found in roles.values] == [MODS]
    assert isinstance(roles.values[0], Role)
    assert [type(found) for found in mentionables.values] == [User, Role]
    [picked] = channels.values
    assert isinstance(picked, TextChannel)


def test_nothing_chosen_yet_means_no_values() -> None:
    assert UserSelect().values == []
    assert RoleSelect().values == []
    assert MentionableSelect().values == []
    assert ChannelSelect().values == []


async def test_the_decorator_builds_the_select_class_asked_for() -> None:
    class Picks(View):
        def __init__(self) -> None:
            super().__init__(timeout=None)
            self.seen: list[object] = []

        @select(cls=RoleSelect, custom_id="roles", max_values=3)
        async def roles(self, interaction: Interaction, picked: RoleSelect) -> None:
            del interaction
            self.seen.extend(picked.values)

        @select(cls=ChannelSelect, custom_id="channels", channel_types=[ChannelType.GUILD_VOICE])
        async def channels(self, interaction: Interaction, picked: ChannelSelect) -> None:
            del interaction, picked

        @select(cls=Select, custom_id="strings", options=[SelectOption(label="a", value="a")])
        async def strings(self, interaction: Interaction, picked: Select) -> None:
            del interaction, picked

    view = Picks()
    kinds = {item.custom_id: item for item in view.children}
    assert isinstance(kinds["roles"], RoleSelect)
    assert isinstance(kinds["channels"], ChannelSelect)
    assert kinds["channels"].channel_types == [ChannelType.GUILD_VOICE]
    assert isinstance(kinds["strings"], Select)
    client, _ = await started()
    client.add_view(view)
    resolved: Json = {"roles": {str(MODS): role(MODS, "mods", position=2)}}
    await client.process_interaction(payload(chosen("roles", 6, [str(MODS)], resolved)))
    for _ in range(10):
        await asyncio.sleep(0)
    assert [found.id for found in view.seen if isinstance(found, Role)] == [MODS]
