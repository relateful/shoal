from typing import Literal, override

import msgspec
import pytest

from shoal import app_commands
from shoal.app_commands import (
    CommandAlreadyRegisteredError,
    CommandSignatureMismatchError,
    CommandSyncFailureError,
    CommandTree,
    Group,
    TranslationContext,
    TranslationContextLocation,
    TranslationError,
    Translator,
    locale_str,
)
from shoal.client.interaction import Interaction
from shoal.models.user import User
from shoal.payloads import Locale, OverwriteCommandParams
from shoal.rest.errors import BadRequestError
from tests.support.client import started
from tests.support.fakes import FakeTransport, settle
from tests.support.interactions import command, option, payload

FRENCH: dict[str, str] = {
    "greet": "saluer",
    "Say hello": "Dire bonjour",
    "loud": "fort",
    "How loud": "À quel point",
    "Yes": "Oui",
    "tags": "etiquettes",
    "show": "montrer",
    "Inspect": "Inspecter",
}


class French(Translator):
    def __init__(self) -> None:
        self.events: list[str] = []
        self.locations: set[TranslationContextLocation] = set()

    @override
    async def load(self) -> None:
        self.events.append("load")

    @override
    async def unload(self) -> None:
        self.events.append("unload")

    @override
    async def translate(self, string: locale_str, locale: Locale, context: TranslationContext) -> str | None:
        self.locations.add(context.location)
        return FRENCH.get(string.message) if locale is Locale.FRENCH else None


async def greet(interaction: Interaction, loud: Literal["Yes", "No"] = "No") -> None:
    del interaction, loud


def sent(transport: FakeTransport) -> list[OverwriteCommandParams]:
    body = transport.requests[-1].body
    assert body is not None
    return msgspec.json.decode(body, type=list[OverwriteCommandParams])


async def test_a_translator_localizes_every_name_and_description_on_sync() -> None:
    client, transport = await started()
    tree = CommandTree(client)
    translator = French()
    await tree.set_translator(translator)
    assert tree.translator is translator
    made = app_commands.describe(loud="How loud")(app_commands.command(description="Say hello")(greet))
    tree.add_command(made)
    tags = Group(name="tags", description="Saved answers")
    tags.command(name="show", description="Show one")(greet)
    tree.add_command(tags)

    @tree.context_menu(name="Inspect")
    async def inspect_user(interaction: Interaction, target: User) -> None:
        del interaction, target

    transport.queue(200, [])
    await tree.sync()
    greet_sent, tags_sent, menu_sent = sent(transport)
    assert greet_sent.name_localizations == {Locale.FRENCH: "saluer"}
    assert greet_sent.description_localizations == {Locale.FRENCH: "Dire bonjour"}
    assert isinstance(greet_sent.options, list)
    [loud] = greet_sent.options
    assert loud.name_localizations == {Locale.FRENCH: "fort"}
    assert loud.description_localizations == {Locale.FRENCH: "À quel point"}
    assert isinstance(loud.choices, list)
    yes, no = loud.choices
    assert (yes.name, yes.name_localizations) == ("Yes", {Locale.FRENCH: "Oui"})
    assert no.name_localizations is msgspec.UNSET
    assert tags_sent.name_localizations == {Locale.FRENCH: "etiquettes"}
    assert tags_sent.description_localizations is msgspec.UNSET
    assert isinstance(tags_sent.options, list)
    assert tags_sent.options[0].name_localizations == {Locale.FRENCH: "montrer"}
    assert menu_sent.name_localizations == {Locale.FRENCH: "Inspecter"}
    assert translator.locations == set(TranslationContextLocation)
    await tree.set_translator(None)
    assert translator.events == ["load", "unload"]


async def test_a_translator_that_raises_stops_the_sync() -> None:
    class Broken(Translator):
        @override
        async def translate(
            self, string: locale_str, locale: Locale, context: TranslationContext
        ) -> str | None:
            raise LookupError(string.message)

    client, _ = await started()
    tree = CommandTree(client)
    tree.command(description="Say hello")(greet)
    await tree.set_translator(Broken())
    with pytest.raises(TranslationError, match="translating 'greet'") as raised:
        await tree.sync()
    assert isinstance(raised.value.original, LookupError)


def test_a_locale_string_reads_as_its_message() -> None:
    hello = locale_str("hello", key="greeting")
    assert (str(hello), hello.extras, repr(hello)) == ("hello", {"key": "greeting"}, "locale_str('hello')")
    assert hello == locale_str("hello")
    assert hello != "hello"
    assert hash(hello) == hash(locale_str("hello"))


async def test_a_refused_sync_names_the_commands_discord_refused() -> None:
    client, transport = await started()
    tree = CommandTree(client)
    tree.command(name="first", description="A")(greet)
    tree.command(name="second", description="B")(greet)
    errors = {"1": {"name": {"_errors": [{"code": "APPLICATION_COMMAND_INVALID_NAME", "message": "bad"}]}}}
    transport.queue(400, {"code": 50035, "message": "Invalid Form Body", "errors": errors})
    with pytest.raises(CommandSyncFailureError) as raised:
        await tree.sync()
    assert isinstance(raised.value, BadRequestError)
    assert raised.value.commands == ["second"]


async def test_registering_a_name_twice_and_out_of_date_commands() -> None:
    client, _ = await started()
    tree = CommandTree(client)
    tree.command(description="Say hello")(greet)
    with pytest.raises(
        CommandAlreadyRegisteredError, match="'greet' is already registered globally"
    ) as raised:
        tree.command(description="Again")(greet)
    assert isinstance(raised.value, ValueError)
    errors: list[Exception] = []

    @tree.error
    async def record(interaction: Interaction, error: Exception) -> None:
        del interaction
        errors.append(error)

    await client.process_interaction(payload(command("greet", option("removed", "x"))))
    await settle()
    assert [type(error) for error in errors] == [CommandSignatureMismatchError]


def test_install_and_context_decorators_stack() -> None:
    @app_commands.guild_install()
    @app_commands.user_install()
    @app_commands.user_install()
    @app_commands.dm_only()
    @app_commands.private_channel_only()
    @app_commands.command(description="Everywhere")
    async def everywhere(interaction: Interaction) -> None:
        del interaction

    sent_payload = msgspec.json.decode(msgspec.json.encode(everywhere.to_payload()))
    assert sent_payload["integration_types"] == [1, 0]
    assert sent_payload["contexts"] == [2, 1]

    @app_commands.private_channel_only()
    @app_commands.dm_only()
    async def pending(interaction: Interaction) -> None:
        del interaction

    made = app_commands.command(description="Pending")(pending)
    assert msgspec.json.decode(msgspec.json.encode(made.to_payload()))["contexts"] == [1, 2]
