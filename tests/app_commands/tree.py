import logging
from typing import override

import msgspec
import pytest

from shoal import app_commands
from shoal.app_commands.commands import Command, Group
from shoal.app_commands.errors import (
    CheckFailureError,
    CommandInvokeError,
    CommandLimitReachedError,
    CommandNotFoundError,
    CommandSignatureMismatchError,
    NoPrivateMessageError,
)
from shoal.app_commands.models import Choice, Namespace
from shoal.app_commands.tree import CommandTree
from shoal.client.client import Client, ClientError
from shoal.client.interaction import Interaction
from shoal.models.member import Member
from shoal.models.message import Message
from shoal.models.user import User
from shoal.payloads import APPLICATION_MAX_COMMANDS, ApplicationCommandType
from tests.support.client import INTENTS, started
from tests.support.fakes import FakeTransport, SentRequest, settle
from tests.support.interactions import autocomplete, command, common, option, payload
from tests.support.models import ALICE, APPLICATION, BOB, GUILD, member, message, user

type Json = dict[str, object]
type Seen = list[tuple[str, object]]


def sub(name: str, *options: Json, group: bool = False) -> Json:
    """A subcommand option, or a subcommand group with `group`."""
    return {"name": name, "type": 2 if group else 1, "options": list(options)}


def context(kind: int, target: int, resolved: Json) -> Json:
    """A user (`kind` 2) or message (3) command used on `target`."""
    data: Json = {"id": "20", "name": "Inspect", "type": kind, "target_id": str(target), "resolved": resolved}
    return common() | {"type": 2, "data": data}


def sent(request: SentRequest) -> object:
    assert request.body is not None
    return msgspec.json.decode(request.body)


class Suggestions(msgspec.Struct):
    choices: list[dict[str, str]]


class AutocompleteAnswer(msgspec.Struct):
    """The autocomplete response a tree sends."""

    type: int
    data: Suggestions


async def ping(interaction: Interaction) -> None:
    del interaction


async def setup() -> tuple[Client, FakeTransport, CommandTree, Seen]:
    """A started client with a tree, and a list for callbacks to record what they saw."""
    client, transport = await started()
    return client, transport, CommandTree(client), []


def test_commands_register_globally_or_per_guild() -> None:
    tree = CommandTree(Client(intents=INTENTS))
    first = Command(callback=ping)
    tree.add_command(first)
    tree.add_command(Command(callback=ping), guild=GUILD)
    assert tree.get_command("ping") is first
    assert tree.get_command("ping", guild=GUILD) is not first
    assert tree.get_command("ping", guild=99) is None
    with pytest.raises(ValueError, match="already registered"):
        tree.add_command(Command(callback=ping))
    replacement = Command(callback=ping)
    tree.add_command(replacement, override=True)
    assert tree.get_commands() == [replacement]
    assert tree.remove_command("ping") is replacement
    assert tree.get_commands() == []
    tree.clear_commands(guild=GUILD)
    assert tree.get_commands(guild=GUILD) == []
    assert repr(tree) == "<CommandTree global=0 guild=0>"


def test_commands_go_where_guilds_says_unless_told_otherwise() -> None:
    tree = CommandTree(Client(intents=INTENTS))

    @app_commands.guilds(1, 2)
    @app_commands.command()
    async def local(interaction: Interaction) -> None:
        del interaction

    tree.add_command(local)
    assert tree.get_commands() == []
    assert tree.get_commands(guild=1) == [local]
    assert tree.get_commands(guild=2) == [local]


def test_a_command_can_be_discarded_from_everywhere_it_was_added() -> None:
    tree = CommandTree(Client(intents=INTENTS))
    everywhere = Command(callback=ping)
    tree.add_command(everywhere)
    tree.add_command(everywhere, guilds=[1, 2])
    other = Command(callback=ping)
    tree.add_command(other, guild=3)
    assert tree.get_all_commands() == [everywhere, other]
    tree.discard(everywhere)
    tree.discard(everywhere)
    assert tree.get_all_commands() == [other]
    assert tree.get_command("ping", guild=3) is other


def test_a_context_menu_and_a_slash_command_can_share_a_name() -> None:
    tree = CommandTree(Client(intents=INTENTS))

    @tree.context_menu(name="ping")
    async def profile(interaction: Interaction, member: Member) -> None:
        del interaction, member

    slash = tree.command()(ping)
    assert tree.get_command("ping") is slash
    assert tree.get_command("ping", type=ApplicationCommandType.USER) is profile
    assert tree.get_commands(type=ApplicationCommandType.USER) == [profile]


def test_subcommands_are_added_through_their_group() -> None:
    tree = CommandTree(Client(intents=INTENTS))
    group = Group(name="settings")
    child = group.command()(ping)
    with pytest.raises(ValueError, match="add the group instead"):
        tree.add_command(child)
    tree.add_command(group)
    assert [item.name for item in tree.walk_commands()] == ["settings", "ping"]


def test_the_number_of_commands_is_limited_as_discord_limits_it() -> None:
    tree = CommandTree(Client(intents=INTENTS))
    for index in range(APPLICATION_MAX_COMMANDS[ApplicationCommandType.CHAT_INPUT]):
        tree.add_command(Command(callback=ping, name=f"c{index}"))
    with pytest.raises(ValueError, match="100 CHAT_INPUT"):
        tree.add_command(Command(callback=ping, name="extra"))
    tree.add_command(Command(callback=ping, name="extra"), guild=GUILD)
    with pytest.raises(CommandLimitReachedError, match="in guild 10 is the most Discord allows"):
        tree.copy_global_to(guild=GUILD)


def test_global_commands_can_be_copied_to_a_guild() -> None:
    tree = CommandTree(Client(intents=INTENTS))
    slash = tree.command()(ping)
    tree.copy_global_to(guild=GUILD)
    assert tree.get_commands(guild=GUILD) == [slash]


async def test_sync_overwrites_the_commands_in_discord() -> None:
    client, transport = await started()
    tree = CommandTree(client)
    tree.command(description="Pong")(ping)
    transport.queue(200, [])
    transport.queue(200, [])
    assert await tree.sync() == []
    assert await tree.sync(guild=GUILD) == []
    global_sync, guild_sync = transport.requests[-2:]
    assert global_sync.method == "PUT"
    assert global_sync.url.endswith(f"/applications/{APPLICATION}/commands")
    assert sent(global_sync) == [{"name": "ping", "description": "Pong", "type": 1}]
    assert guild_sync.url.endswith(f"/applications/{APPLICATION}/guilds/{GUILD}/commands")
    assert sent(guild_sync) == []


async def test_sync_needs_a_logged_in_client() -> None:
    with pytest.raises(ClientError, match="log in"):
        await CommandTree(Client(intents=INTENTS)).sync()


async def test_a_command_receives_its_options_converted() -> None:
    client, _, tree, seen = await setup()

    @tree.command()
    async def ban(interaction: Interaction, member: Member, reason: str | None = None, days: int = 1) -> None:
        seen.extend(
            [
                ("call", (member.id, reason, days)),
                ("namespace", interaction.namespace),
                ("command", interaction.command),
            ]
        )

    partial = {key: value for key, value in member(BOB, "bob").items() if key != "user"}
    resolved: Json = {"users": {str(BOB): user(BOB, "bob")}, "members": {str(BOB): partial}}
    member_option: Json = {"name": "member", "type": 6, "value": str(BOB)}
    await client.process_interaction(
        payload(command("ban", member_option, option("reason", "spam"), resolved=resolved))
    )
    await settle()
    assert seen[0] == ("call", (BOB, "spam", 1))
    namespace = seen[1][1]
    assert isinstance(namespace, Namespace)
    assert isinstance(namespace.member, Member)
    assert namespace.reason == "spam"
    assert "days" not in namespace
    assert seen[2] == ("command", ban)


class Tags(Group, name="tags"):
    def __init__(self, seen: Seen) -> None:
        super().__init__()
        self.seen = seen

    @app_commands.command()
    async def show(self, interaction: Interaction, name: str) -> None:
        del interaction
        self.seen.append(("show", name))

    @show.autocomplete("name")
    async def suggest(self, interaction: Interaction, current: str) -> list[Choice[str]]:
        del interaction
        self.seen.append(("suggest", current))
        return [Choice(name=f"{current}-{index}", value=f"{current}{index}") for index in range(30)]

    class Admin(Group):
        @app_commands.command()
        async def wipe(self, interaction: Interaction) -> None:
            interaction.extras["wiped"] = self.qualified_name


async def test_subcommands_run_bound_to_their_group() -> None:
    client, _, tree, seen = await setup()
    tree.add_command(Tags(seen))
    await client.process_interaction(payload(command("tags", sub("show", option("name", "faq")))))
    wiped = await client.process_interaction(payload(command("tags", sub("admin", sub("wipe"), group=True))))
    await settle()
    assert seen == [("show", "faq")]
    assert wiped.extras["wiped"] == "tags admin"


async def test_autocomplete_suggests_at_most_25_choices() -> None:
    client, transport, tree, seen = await setup()
    tree.add_command(Tags(seen))
    transport.queue(204)
    await client.process_interaction(
        payload(autocomplete("tags", sub("show", option("name", "fa", focused=True))))
    )
    await settle()
    assert seen == [("suggest", "fa")]
    callback = transport.requests[-1]
    assert callback.url.endswith("/callback")
    assert callback.body is not None
    answer = msgspec.json.decode(callback.body, type=AutocompleteAnswer)
    assert answer.type == 8
    assert len(answer.data.choices) == 25
    assert answer.data.choices[0] == {"name": "fa-0", "value": "fa0"}


async def test_context_menus_receive_their_target() -> None:
    client, _, tree, seen = await setup()

    @tree.context_menu(name="Inspect")
    async def inspect_user(interaction: Interaction, target: Member | User) -> None:
        del interaction
        seen.append(("user", target))

    member_payload: Json = {"users": {str(BOB): user(BOB, "bob")}}
    await client.process_interaction(payload(context(2, BOB, member_payload)))
    tree.remove_command("Inspect", type=ApplicationCommandType.USER)

    @tree.context_menu(name="Inspect")
    async def inspect_message(interaction: Interaction, target: Message) -> None:
        del interaction
        seen.append(("message", target))

    message_payload: Json = {"messages": {"77": message(77)}}
    await client.process_interaction(payload(context(3, 77, message_payload)))
    await settle()
    assert [kind for kind, _ in seen] == ["user", "message"]
    assert isinstance(seen[0][1], User)
    target = seen[1][1]
    assert isinstance(target, Message)
    assert target.id == 77
    assert inspect_user.type is ApplicationCommandType.USER
    assert inspect_message.type is ApplicationCommandType.MESSAGE


async def test_errors_reach_the_command_its_groups_and_then_the_tree() -> None:
    client, _, tree, seen = await setup()
    group = Group(name="admin")

    @group.command()
    async def fail(interaction: Interaction) -> None:
        del interaction
        msg = "boom"
        raise RuntimeError(msg)

    @fail.error
    async def on_command_error(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("command", error))

    @group.error
    async def on_group_error(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("group", error))

    @tree.error
    async def on_tree_error(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("tree", error))

    tree.add_command(group)
    await client.process_interaction(payload(command("admin", sub("fail"))))
    await settle()
    assert [where for where, _ in seen] == ["command", "group", "tree"]
    error = seen[0][1]
    assert isinstance(error, CommandInvokeError)
    assert isinstance(error.original, RuntimeError)
    assert error.command_name == "admin fail"


async def test_unhandled_errors_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    client, _, tree, _ = await setup()

    @tree.command()
    async def broken(interaction: Interaction) -> None:
        del interaction
        msg = "boom"
        raise RuntimeError(msg)

    with caplog.at_level(logging.ERROR, logger="shoal.app_commands"):
        await client.process_interaction(payload(command("broken")))
        await settle()
    assert "command 'broken' raised" in caplog.text


async def test_a_handler_returning_true_stops_the_error_there(caplog: pytest.LogCaptureFixture) -> None:
    client, _, tree, _ = await setup()
    seen: list[Exception] = []

    @tree.command()
    async def broken(interaction: Interaction) -> None:
        del interaction
        msg = "boom"
        raise RuntimeError(msg)

    @broken.error
    async def handled(interaction: Interaction, error: Exception) -> bool:
        del interaction
        seen.append(error)
        return True

    with caplog.at_level(logging.ERROR, logger="shoal.app_commands"):
        await client.process_interaction(payload(command("broken")))
        await settle()
    assert len(seen) == 1
    assert "command 'broken' raised" not in caplog.text


async def test_a_failing_error_handler_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    client, _, tree, _ = await setup()

    @tree.error
    async def clumsy(interaction: Interaction, error: Exception) -> None:
        del interaction, error
        msg = "handler broke"
        raise ValueError(msg)

    with caplog.at_level(logging.ERROR, logger="shoal.app_commands"):
        await client.process_interaction(payload(command("missing")))
        await settle()
    assert "an error handler raised" in caplog.text


async def test_unknown_commands_are_reported() -> None:
    client, _, tree, seen = await setup()
    tree.add_command(Group(name="empty"))

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("error", error))

    await client.process_interaction(payload(command("gone")))
    await client.process_interaction(payload(command("empty", sub("nothing"))))
    await client.process_interaction(payload(autocomplete("gone")))
    await settle()
    errors = [error for _, error in seen]
    assert len(errors) == 2
    assert all(isinstance(error, CommandNotFoundError) for error in errors)
    assert isinstance(errors[1], CommandNotFoundError)
    assert errors[1].name == "empty nothing"


async def test_checks_refuse_before_the_callback_runs() -> None:
    client, _, tree, seen = await setup()

    class Closed(Group, name="closed"):
        @override
        async def interaction_check(self, interaction: Interaction) -> bool:
            del interaction
            return False

        @app_commands.command()
        async def inside(self, interaction: Interaction) -> None:
            del interaction
            seen.append(("ran", "inside"))

    @app_commands.guild_only()
    @app_commands.command()
    async def local(interaction: Interaction) -> None:
        del interaction
        seen.append(("ran", "local"))

    @app_commands.check(lambda interaction: interaction.user.id != ALICE)
    @app_commands.command()
    async def not_alice(interaction: Interaction) -> None:
        del interaction
        seen.append(("ran", "not_alice"))

    @tree.command()
    async def needs(interaction: Interaction, value: int) -> None:
        del interaction, value
        seen.append(("ran", "needs"))

    for item in (Closed(), local, not_alice):
        tree.add_command(item)

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("error", type(error)))

    await client.process_interaction(payload(command("closed", sub("inside"))))
    await client.process_interaction(payload(command("local", in_guild=False)))
    await client.process_interaction(payload(command("not_alice")))
    await client.process_interaction(payload(command("needs")))
    await settle()
    assert seen == [
        ("error", CheckFailureError),
        ("error", NoPrivateMessageError),
        ("error", CheckFailureError),
        ("error", CommandSignatureMismatchError),
    ]


async def test_the_tree_check_applies_to_every_command() -> None:
    class Locked(CommandTree):
        @override
        async def interaction_check(self, interaction: Interaction) -> bool:
            del interaction
            return False

    client, _ = await started()
    tree = Locked(client)
    assert tree.client is client
    tree.command()(ping)
    errors: list[Exception] = []

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        errors.append(error)

    await client.process_interaction(payload(command("ping")))
    await settle()
    assert len(errors) == 1
    assert isinstance(errors[0], CheckFailureError)


async def test_a_user_command_in_a_guild_receives_a_member() -> None:
    client, _, tree, seen = await setup()

    @tree.context_menu(name="Inspect")
    async def inspect(interaction: Interaction, target: Member) -> None:
        del interaction
        seen.append(("target", target))

    partial = {key: value for key, value in member(BOB, "bob").items() if key != "user"}
    sent: Json = {"users": {str(BOB): user(BOB, "bob")}, "members": {str(BOB): partial}}
    await client.process_interaction(payload(context(2, BOB, sent)))
    await settle()
    target = seen[0][1]
    assert isinstance(target, Member)
    assert inspect.qualified_name == "Inspect"


async def test_a_context_menu_without_its_target_reports_it() -> None:
    client, _, tree, seen = await setup()

    @tree.context_menu(name="Inspect")
    async def inspect(interaction: Interaction, target: Message) -> None:
        del interaction, target

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("error", str(error)))

    await client.process_interaction(payload(context(3, 77, {})))
    await client.process_interaction(payload(context(3, 77, {"messages": {}})))
    tree.remove_command("Inspect", type=ApplicationCommandType.MESSAGE)
    tree.context_menu(name="Inspect")(on_user)
    await client.process_interaction(payload(context(2, BOB, {"users": {}})))
    await settle()
    assert [text for _, text in seen] == [
        "option 'target': cannot use 77: the message was not sent",
        "option 'target': cannot use 77: the message was not sent",
        "option 'target': cannot use 4: the user was not sent",
    ]


async def on_user(interaction: Interaction, target: User) -> None:
    del interaction, target


async def test_guild_commands_answer_only_in_their_guild() -> None:
    client, _, tree, seen = await setup()

    @tree.command(guild=GUILD)
    async def local(interaction: Interaction) -> None:
        del interaction
        seen.append(("ran", "local"))

    guild_command = command("local")
    guild_command["data"] = {"id": "20", "name": "local", "type": 1, "guild_id": str(GUILD)}
    await client.process_interaction(payload(guild_command))
    await settle()
    assert seen == [("ran", "local")]


async def test_command_errors_raised_by_a_callback_are_not_wrapped() -> None:
    client, _, tree, seen = await setup()

    @tree.command()
    async def refuse(interaction: Interaction) -> None:
        del interaction
        msg = "not today"
        raise CheckFailureError(msg)

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("error", error))

    await client.process_interaction(payload(command("refuse")))
    await settle()
    assert isinstance(seen[0][1], CheckFailureError)


async def test_autocomplete_without_a_callback_suggests_nothing() -> None:
    client, transport, tree, _ = await setup()

    @tree.command()
    async def tag(interaction: Interaction, name: str, count: int = 1) -> None:
        del interaction, name, count

    transport.queue(204)
    focused = option("name", "f", focused=True)
    await client.process_interaction(
        payload(autocomplete("tag", focused, {"name": "count", "type": 4, "value": 3}))
    )
    await client.process_interaction(payload(autocomplete("tag", option("other", "x", focused=True))))
    await client.process_interaction(payload(autocomplete("tag")))
    await settle()
    answer = msgspec.json.decode(sent_body(transport.requests[-1]), type=AutocompleteAnswer)
    assert answer.data.choices == []


def sent_body(request: SentRequest) -> bytes:
    assert request.body is not None
    return request.body


async def test_autocomplete_sees_the_other_options_and_reports_its_errors() -> None:
    client, _, tree, seen = await setup()

    @tree.command()
    async def give(interaction: Interaction, member: Member, item: str) -> None:
        del interaction, member, item

    @give.autocomplete("item")
    async def suggest(interaction: Interaction, current: str) -> list[Choice[str]]:
        namespace = interaction.namespace
        assert isinstance(namespace, Namespace)
        seen.append(("member", namespace.member))
        seen.append(("current", current))
        msg = "no items"
        raise LookupError(msg)

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        seen.append(("error", type(error)))

    unresolved: Json = {"name": "member", "type": 6, "value": str(BOB)}
    await client.process_interaction(
        payload(autocomplete("give", unresolved, option("item", "sw", focused=True)))
    )
    await settle()
    assert seen == [("member", str(BOB)), ("current", "sw"), ("error", LookupError)]
