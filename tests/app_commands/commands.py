import inspect
from typing import cast

import msgspec
import pytest

from shoal import app_commands
from shoal.app_commands.commands import (
    NO_DESCRIPTION,
    Command,
    CommandCallback,
    ContextMenu,
    ContextMenuCallback,
    Group,
)
from shoal.app_commands.models import Choice, Range
from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.models.member import Member
from shoal.models.message import Message
from shoal.models.user import User
from shoal.payloads import ApplicationCommandType, Permissions
from tests.support.client import started
from tests.support.interactions import command, payload


def body(command: Command | Group | ContextMenu) -> dict[str, object]:
    return msgspec.json.decode(encode_json(command.to_payload()), type=dict[str, object])


async def ban(interaction: Interaction, member: Member, days: Range[int, 0, 7] = 1) -> None:
    """Ban a member.

    Args:
        member: Who to ban.
        days: How many days of messages to delete.
    """
    del interaction, member, days


def test_a_command_takes_its_name_description_and_options_from_the_function() -> None:
    created = Command(callback=ban)
    assert created.name == "ban"
    assert created.qualified_name == "ban"
    assert body(created) == {
        "name": "ban",
        "description": "Ban a member.",
        "type": 1,
        "options": [
            {"type": 6, "name": "member", "description": "Who to ban.", "required": True},
            {
                "type": 4,
                "name": "days",
                "description": "How many days of messages to delete.",
                "min_value": 0,
                "max_value": 7,
            },
        ],
    }
    assert repr(created) == "<Command name='ban' parameters=2>"


def test_a_command_without_a_docstring_gets_the_placeholder_description() -> None:
    async def ping(interaction: Interaction) -> None:
        del interaction

    assert Command(callback=ping).description == NO_DESCRIPTION
    assert Command(callback=ping, name="pong", description="Pong").description == "Pong"


def test_commands_are_checked_when_made() -> None:
    def sync(interaction: Interaction) -> None:
        del interaction

    async def nothing() -> None:
        pass

    async def unhinted(interaction: Interaction, value: int) -> None:
        del interaction, value

    del unhinted.__annotations__["value"]

    async def misordered(interaction: Interaction, first: int = 1, second: int = 2, *, third: int) -> None:
        del interaction, first, second, third

    with pytest.raises(TypeError, match="must be async"):
        Command(callback=cast("CommandCallback", sync))
    with pytest.raises(TypeError, match="interaction as its first"):
        Command(callback=nothing)
    with pytest.raises(TypeError, match="needs a type hint"):
        Command(callback=unhinted)
    with pytest.raises(TypeError, match="must come before optional"):
        Command(callback=misordered)
    with pytest.raises(ValueError, match="not a valid command"):
        Command(callback=ban, name="Has Spaces")


def test_decorators_apply_before_and_after_the_command_is_made() -> None:
    @app_commands.describe(colour="Pick one")
    @app_commands.rename(colour="color")
    @app_commands.command(description="Paint")
    @app_commands.choices(colour=[Choice(name="Red", value="red")])
    async def paint(interaction: Interaction, colour: str) -> None:
        del interaction, colour

    assert body(paint)["options"] == [
        {
            "type": 3,
            "name": "color",
            "description": "Pick one",
            "required": True,
            "choices": [{"name": "Red", "value": "red"}],
        }
    ]
    with pytest.raises(KeyError):
        app_commands.describe(missing="x")(paint)


def test_permission_and_context_decorators_reach_the_payload() -> None:
    @app_commands.guild_only()
    @app_commands.nsfw()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.guilds(10, 11)
    @app_commands.command()
    async def purge(interaction: Interaction) -> None:
        del interaction

    sent = body(purge)
    assert sent["contexts"] == [0]
    assert sent["nsfw"] is True
    assert sent["default_member_permissions"] == "4"
    assert sent["integration_types"] == [0, 1]
    assert purge.guild_ids == [10, 11]

    @app_commands.command()
    @app_commands.allowed_contexts(dms=True, private_channels=True)
    async def anywhere(interaction: Interaction) -> None:
        del interaction

    assert body(anywhere)["contexts"] == [1, 2]


def test_autocomplete_can_be_attached_to_a_made_command() -> None:
    @app_commands.command()
    async def tag(interaction: Interaction, name: str) -> None:
        del interaction, name

    @tag.autocomplete("name")
    async def suggest(interaction: Interaction, current: str) -> list[Choice[str]]:
        del interaction
        return [Choice(name=current, value=current)]

    parameter = tag.get_parameter("name")
    assert parameter is not None
    assert parameter.autocomplete is suggest
    assert body(tag)["options"] == [
        {
            "type": 3,
            "name": "name",
            "description": "No description given",
            "required": True,
            "autocomplete": True,
        }
    ]
    with pytest.raises(KeyError):
        tag.autocomplete("missing")


class Tags(Group, name="tags", description="Server tags", guild_only=True):
    def __init__(self) -> None:
        super().__init__()
        self.shown: list[str] = []

    @app_commands.command(description="Show a tag")
    async def show(self, interaction: Interaction, name: str) -> None:
        del interaction
        self.shown.append(name)

    class Admin(Group, description="Manage tags"):
        @app_commands.command(description="Delete a tag")
        async def delete(self, interaction: Interaction, name: str) -> None:
            del interaction, name


def test_a_group_subclass_collects_its_commands_and_subgroups() -> None:
    tags = Tags()
    assert [child.name for child in tags.commands] == ["show", "admin"]
    show = tags.get_command("show")
    assert isinstance(show, Command)
    assert show.binding is tags
    assert show.qualified_name == "tags show"
    assert show is not Tags.show
    assert [item.name for item in tags.walk_commands()] == ["show", "admin", "delete"]
    sent = body(tags)
    assert sent["contexts"] == [0]
    assert sent["options"] == [
        {
            "type": 1,
            "name": "show",
            "description": "Show a tag",
            "options": [{"type": 3, "name": "name", "description": "No description given", "required": True}],
        },
        {
            "type": 2,
            "name": "admin",
            "description": "Manage tags",
            "options": [
                {
                    "type": 1,
                    "name": "delete",
                    "description": "Delete a tag",
                    "options": [
                        {"type": 3, "name": "name", "description": "No description given", "required": True}
                    ],
                }
            ],
        },
    ]
    assert repr(tags) == "<Tags name='tags' commands=2>"


def test_groups_made_directly_take_commands() -> None:
    settings = Group(name="settings", description="Settings")

    @settings.command(description="Show settings")
    async def show(interaction: Interaction) -> None:
        del interaction

    assert settings.get_command("show") is show
    assert show.parent is settings
    with pytest.raises(ValueError, match="already has"):
        settings.add_command(Command(callback=show.callback))
    assert settings.remove_command("show") is show
    assert settings.commands == []


def test_groups_hold_at_most_25_commands_one_level_deep() -> None:
    crowded = Group(name="crowded")
    for index in range(25):
        crowded.add_command(Group(name=f"g{index}"))
    with pytest.raises(ValueError, match="25 subcommands"):
        crowded.add_command(Group(name="extra"))
    outer, inner = Group(name="outer"), Group(name="inner")
    outer.add_command(inner)
    with pytest.raises(ValueError, match="one level deep"):
        inner.add_command(Group(name="deeper"))
    nested = Group(name="nested").add_command(Group(name="child"))
    with pytest.raises(ValueError, match="one level deep"):
        Group(name="top").add_command(nested)
    with pytest.raises(ValueError, match="already belongs"):
        Group(name="other").add_command(inner)


def test_context_menus_take_their_type_from_the_target() -> None:
    async def profile(interaction: Interaction, member: Member) -> None:
        del interaction, member

    async def quote(interaction: Interaction, message: Message) -> None:
        del interaction, message

    async def anyone(interaction: Interaction, user: Member | User) -> None:
        del interaction, user

    assert ContextMenu(name="Profile", callback=profile).type is ApplicationCommandType.USER
    assert ContextMenu(name="Quote", callback=quote).type is ApplicationCommandType.MESSAGE
    assert ContextMenu(name="Anyone", callback=anyone).type is ApplicationCommandType.USER
    menu = app_commands.context_menu(name="Quote this")(quote)
    assert body(menu) == {"name": "Quote this", "type": 3}
    assert repr(menu) == "<ContextMenu name='Quote this' type=MESSAGE>"


def test_context_menus_are_checked_when_made() -> None:
    async def wrong(interaction: Interaction, target: str) -> None:
        del interaction, target

    async def lonely(interaction: Interaction) -> None:
        del interaction

    with pytest.raises(TypeError, match="Message, Member or User"):
        ContextMenu(name="Wrong", callback=wrong)
    with pytest.raises(TypeError, match=r"\(interaction, target\)"):
        ContextMenu(name="Lonely", callback=lonely)
    with pytest.raises(ValueError, match="1 to 32"):
        ContextMenu(name="x" * 33, callback=wrong)


class Undocumented(Group):
    pass


class Settings(
    Group, name="settings", description="Settings", guild_only=True, default_permissions=Permissions(0)
):
    """Bot settings."""


class Roles(Settings):
    """Role settings."""


def test_a_group_describes_itself_only_with_its_own_docstring() -> None:
    assert Undocumented().description == NO_DESCRIPTION
    assert Settings().description == "Settings"
    assert Roles().description == "Role settings."


def test_group_settings_are_inherited_but_not_the_name() -> None:
    roles = Roles()
    assert roles.name == "roles"
    assert roles.guild_only
    assert roles.default_permissions == 0


def test_no_default_permissions_means_administrators_only() -> None:
    sent = body(Settings())
    assert sent["default_member_permissions"] == "0"
    assert body(Group(name="open", default_permissions=Permissions(0)))["default_member_permissions"] == "0"


def test_descriptions_options_and_choices_are_held_to_discords_limits() -> None:
    with pytest.raises(ValueError, match="Discord takes 1 to 100"):
        Command(callback=ping_command, description="x" * 101)
    with pytest.raises(ValueError, match="at most 25"):
        app_commands.choices(colour=[Choice(name=str(index), value=index) for index in range(26)])(
            paint_command
        )

    async def crowded(interaction: Interaction, **options: int) -> None:
        del interaction, options

    keyword = inspect.Parameter.KEYWORD_ONLY
    first = inspect.Parameter("interaction", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    options = [inspect.Parameter(f"o{index}", keyword, annotation=int) for index in range(26)]
    vars(crowded)["__signature__"] = inspect.Signature([first, *options])
    with pytest.raises(ValueError, match="26 options"):
        Command(callback=crowded)


async def ping_command(interaction: Interaction) -> None:
    del interaction


async def paint_command(interaction: Interaction, colour: int) -> None:
    del interaction, colour


def test_option_decorators_refuse_groups_and_menus() -> None:
    with pytest.raises(TypeError, match="applies to slash commands"):
        app_commands.describe(x="y")(Group(name="g"))


def test_docstring_descriptions_join_continuation_lines() -> None:
    async def report(interaction: Interaction, reason: str) -> None:
        """Report a problem.

        Args:
            interaction: Ignored, as the interaction is not an option.
            reason: What went wrong, in a sentence
                or two.

        Returns:
            Nothing.
        """
        del interaction, reason

    parameter = Command(callback=report).get_parameter("reason")
    assert parameter is not None
    assert parameter.description == "What went wrong, in a sentence or two."


class Suggesting(Group, name="suggesting"):
    @app_commands.command()
    async def show(self, interaction: Interaction, name: str) -> None:
        del interaction, name

    @show.autocomplete("name")
    async def suggest(self, interaction: Interaction, current: str) -> list[Choice[str]]:
        del interaction
        return [Choice(name=f"{current} from {self.name}", value=current)]


async def test_each_group_instance_gets_its_own_commands_and_suggestions() -> None:
    client, _ = await started()
    interaction = await client.process_interaction(payload(command("x")))
    first, second = Suggesting(), Suggesting()
    first_show, second_show = first.get_command("show"), second.get_command("show")
    assert isinstance(first_show, Command)
    assert isinstance(second_show, Command)
    assert first_show.parameters[0] is not second_show.parameters[0]
    first_show.extras["mine"] = True
    assert "mine" not in second_show.extras
    suggest = first_show.parameters[0].autocomplete
    assert suggest is not None
    assert await suggest(interaction, "fa") == [Choice(name="fa from suggesting", value="fa")]


def test_settings_given_before_the_command_is_made_reach_it() -> None:
    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.nsfw()
    @app_commands.guilds(5)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True)
    @app_commands.check(lambda interaction: interaction.guild_id is not None)
    @app_commands.autocomplete(name=suggest_nothing)
    async def configure(interaction: Interaction, name: str) -> None:
        del interaction, name

    sent = body(configure)
    assert sent["nsfw"] is True
    assert sent["default_member_permissions"] == str(1 << 5)
    assert sent["integration_types"] == [1]
    assert sent["contexts"] == [0, 1]
    assert configure.guild_only
    assert configure.guild_ids == [5]
    assert len(configure.checks) == 1
    parameter = configure.get_parameter("name")
    assert parameter is not None
    assert parameter.autocomplete is suggest_nothing


async def suggest_nothing(interaction: Interaction, current: str) -> list[Choice[str]]:
    del interaction, current
    return []


def test_settings_given_after_the_command_is_made_reach_it() -> None:
    made = Command(callback=paint_command)
    for decorate in (
        app_commands.guild_only(),
        app_commands.nsfw(),
        app_commands.guilds(6),
        app_commands.default_permissions(),
        app_commands.allowed_installs(guilds=True),
        app_commands.allowed_contexts(private_channels=True),
        app_commands.rename(colour="color"),
        app_commands.autocomplete(colour=suggest_nothing),
    ):
        decorate(made)
    sent = body(made)
    assert sent["contexts"] == [2]
    assert sent["default_member_permissions"] == "0"
    assert made.guild_ids == [6]
    assert made.parameters[0].display_name == "color"


def test_choice_names_are_held_to_discords_limits() -> None:
    with pytest.raises(ValueError, match="needs a name of 1 to 100"):
        app_commands.choices(colour=[Choice(name="", value=1)])


def test_only_plain_and_keyword_parameters_become_options() -> None:
    async def positional(interaction: Interaction, value: int, /) -> None:
        del interaction, value

    with pytest.raises(TypeError, match="plain or keyword-only"):
        Command(callback=positional)


def test_a_context_menu_callback_must_be_async() -> None:
    def blocking(interaction: Interaction, target: Message) -> None:
        del interaction, target

    with pytest.raises(TypeError, match="must be async"):
        ContextMenu(name="Blocking", callback=cast("ContextMenuCallback", blocking))


def test_a_removed_subcommand_can_join_another_group() -> None:
    first, second = Group(name="first"), Group(name="second")
    moved = first.command()(paint_command)
    assert first.remove_command("paint_command") is moved
    assert first.remove_command("paint_command") is None
    second.add_command(moved)
    assert moved.qualified_name == "second paint_command"


class Restricted(Group, nsfw=True):
    pass


def test_a_group_class_can_be_age_restricted() -> None:
    assert body(Restricted())["nsfw"] is True
