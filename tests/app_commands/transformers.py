from collections.abc import Sequence
from typing import override

import msgspec
import pytest

from shoal import app_commands
from shoal.app_commands import AppCommandError, Choice, CommandTree, Transform, Transformer, TransformerError
from shoal.app_commands.models import AnyChoice
from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.models.member import Member
from shoal.payloads import ApplicationCommandOptionType
from tests.support.client import started
from tests.support.fakes import settle
from tests.support.interactions import autocomplete, command, option, payload
from tests.support.models import BOB, Json, member, user


class Shout(Transformer[str]):
    @property
    @override
    def min_value(self) -> int:
        return 2

    @property
    @override
    def max_value(self) -> int:
        return 10

    @override
    async def transform(self, interaction: Interaction, value: object) -> str:
        if value == "boom":
            msg = "cannot shout that"
            raise ValueError(msg)
        if value == "refuse":
            raise AppCommandError("refused")  # noqa: EM101 - the message is the test
        return f"{value}!".upper()

    @override
    async def autocomplete(self, interaction: Interaction, value: str | float) -> Sequence[AnyChoice]:
        return [Choice(name=f"{value} {index}", value=f"{value}{index}") for index in range(2)]


class Doubled(Transformer[int]):
    @property
    @override
    def type(self) -> ApplicationCommandOptionType:
        return ApplicationCommandOptionType.INTEGER

    @property
    @override
    def choices(self) -> Sequence[AnyChoice]:
        return [Choice(name="one", value=1), Choice(name="two", value=2)]

    @override
    async def transform(self, interaction: Interaction, value: object) -> int:
        assert isinstance(value, int)
        return value * 2


class Nick(Transformer[str]):
    @property
    @override
    def type(self) -> ApplicationCommandOptionType:
        return ApplicationCommandOptionType.USER

    @override
    async def transform(self, interaction: Interaction, value: object) -> str:
        return value.display_name if isinstance(value, Member) else "not a member"


async def test_transformers_shape_the_option_and_convert_the_value() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    seen: list[object] = []

    @tree.command()
    async def say(
        interaction: Interaction,
        text: Transform[str, Shout],
        times: Transform[int, Doubled],
        who: Transform[str, Nick],
        note: Transform[str | None, Shout] = None,
    ) -> None:
        del interaction
        seen.append((text, times, who, note))

    partial = {key: value for key, value in member(BOB, "bob").items() if key != "user"}
    resolved: Json = {"users": {str(BOB): user(BOB, "bob")}, "members": {str(BOB): partial}}
    options = [option("text", "hi"), option("times", 2, 4), option("who", str(BOB), 6)]
    await client.process_interaction(payload(command("say", *options, resolved=resolved)))
    await settle()
    assert seen == [("HI!", 4, "bob", None)]
    sent = msgspec.json.decode(encode_json(say.to_payload()))["options"]
    assert sent[0] == {
        "type": 3,
        "name": "text",
        "description": "…",
        "required": True,
        "min_length": 2,
        "max_length": 10,
        "autocomplete": True,
    }
    assert sent[1]["choices"] == [{"name": "one", "value": 1}, {"name": "two", "value": 2}]
    assert sent[2]["type"] == 6
    assert sent[3].get("required") is None


async def test_transformers_run_after_the_checks_and_report_their_errors() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    errors: list[Exception] = []
    calls: list[str] = []

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        errors.append(error)

    class Counting(Shout):
        @override
        async def transform(self, interaction: Interaction, value: object) -> str:
            calls.append(str(value))
            return await super().transform(interaction, value)

    def not_nope(interaction: Interaction) -> bool:
        return interaction.namespace is None or interaction.namespace.text != "nope"

    @app_commands.check(not_nope)
    @tree.command()
    async def yell(interaction: Interaction, text: Transform[str, Counting]) -> None:
        del interaction, text

    for text in ("nope", "boom", "refuse"):
        await client.process_interaction(payload(command("yell", option("text", text))))
        await settle()
    refused_by_check, wrapped, passed_on = errors
    assert type(refused_by_check).__name__ == "CheckFailureError"
    assert calls == ["boom", "refuse"]
    assert isinstance(wrapped, TransformerError)
    assert "cannot shout that" in str(wrapped)
    assert type(passed_on) is AppCommandError


async def test_a_transformer_class_alone_is_an_annotation_and_suggests() -> None:
    client, transport = await started()
    tree = CommandTree(client)

    @tree.command()
    async def pick(interaction: Interaction, text: Shout) -> None:
        del interaction, text

    assert pick.parameters[0].transformer is not None
    transport.queue(204)
    await client.process_interaction(payload(autocomplete("pick", option("text", "ab", focused=True))))
    await settle()
    assert transport.requests[-1].body is not None
    answer = msgspec.json.decode(transport.requests[-1].body)
    assert answer["data"]["choices"] == [{"name": "ab 0", "value": "ab0"}, {"name": "ab 1", "value": "ab1"}]


def test_transform_takes_a_transformer_only() -> None:
    with pytest.raises(TypeError, match="Transformer"):
        _ = Transform[str, int]
    assert not Doubled().has_autocomplete()
    assert Shout().has_autocomplete()
