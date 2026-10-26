"""Interactions, checked against the interaction data examples in Discord's components reference.

`fixtures/discord_interaction_examples.json` holds those examples verbatim from discord-api-docs, with
JSONC comments, trailing commas and the `...additionalInteractionFields` placeholder removed.
"""

from pathlib import Path

import msgspec
import pytest

from shoal.core.codec import JSONObject, PayloadDecodeError, decode_json, encode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    ActionRow,
    ApplicationCommandInteraction,
    ApplicationCommandOptionChoice,
    ApplicationCommandOptionType,
    ApplicationCommandType,
    ApplicationIntegrationType,
    AutocompleteChoices,
    AutocompleteInteraction,
    AutocompleteResponse,
    Button,
    ButtonStyle,
    ComponentInteraction,
    ComponentType,
    DeferredMessageResponse,
    DeferredUpdateResponse,
    EditWebhookMessageParams,
    Interaction,
    InteractionCallbackResponse,
    InteractionCallbackType,
    InteractionContextType,
    InteractionMessage,
    InteractionType,
    Label,
    LaunchActivityResponse,
    Locale,
    MessageComponentData,
    MessageFlags,
    MessageResponse,
    Modal,
    ModalResponse,
    ModalSubmitData,
    ModalSubmitInteraction,
    PingInteraction,
    PongResponse,
    SendFollowupParams,
    SubmittedLabel,
    SubmittedTextInput,
    TextInput,
    TextInputStyle,
    UnknownComponent,
    UnknownInteraction,
    UpdateMessageResponse,
    parse_interaction,
    parse_submitted_components,
)

EXAMPLES: dict[str, JSONObject] = msgspec.json.decode(
    (Path(__file__).parent / "fixtures" / "discord_interaction_examples.json").read_bytes(),
    type=dict[str, JSONObject],
)
COMPONENT_DATA = sorted(name for name, example in EXAMPLES.items() if example.get("type") == 3)
MODAL_DATA = sorted(name for name, example in EXAMPLES.items() if example.get("type") == 5)

USER: JSONObject = {"id": "3", "username": "u", "discriminator": "0", "global_name": None, "avatar": None}
COMMON: JSONObject = {
    "id": "10",
    "application_id": "11",
    "token": "aW50ZXJhY3Rpb24",
    "version": 1,
    "guild_id": "12",
    "channel_id": "13",
    "member": {
        "user": USER,
        "roles": [],
        "joined_at": "2024-01-01T00:00:00+00:00",
        "deaf": False,
        "mute": False,
        "flags": 0,
        "permissions": "8",
    },
    "app_permissions": "442368",
    "locale": "en-GB",
    "guild_locale": "en-US",
    "entitlements": [],
    "authorizing_integration_owners": {"0": "12"},
    "context": 0,
    "attachment_size_limit": 26214400,
}


KNOWN_INVALID: dict[str, str] = {
    "File Upload: Modal Submit Interaction Data Example": "outside the unsigned 64-bit range",
}
"""Examples that cannot be real payloads, with the reason. Discord's file upload example uses a
21-digit attachment ID, larger than any snowflake can be."""


def interaction_from(value: JSONObject) -> Interaction | UnknownInteraction:
    """Parse an interaction the way it arrives: as JSON bytes."""
    return parse_interaction(msgspec.json.encode(value))


def test_every_example_was_collected() -> None:
    assert len(COMPONENT_DATA) >= 5
    assert len(MODAL_DATA) >= 8


@pytest.mark.parametrize("name", COMPONENT_DATA)
def test_component_data_examples_decode(name: str) -> None:
    data = decode_json(msgspec.json.encode(EXAMPLES[name]["data"]), MessageComponentData)
    assert data.custom_id


@pytest.mark.parametrize("name", MODAL_DATA)
def test_modal_submit_examples_decode_without_unknowns(name: str) -> None:
    raw = msgspec.json.encode(EXAMPLES[name]["data"])
    gap = KNOWN_INVALID.get(name)
    if gap is not None:
        with pytest.raises(PayloadDecodeError, match=gap):
            decode_json(raw, ModalSubmitData)
        return
    data = decode_json(raw, ModalSubmitData)
    submitted = parse_submitted_components(data.components)
    assert submitted
    assert not any(isinstance(component, UnknownComponent) for component in submitted)


def test_a_slash_command_interaction_is_fully_typed() -> None:
    interaction = interaction_from(
        {
            **COMMON,
            "type": 2,
            "data": {
                "id": "20",
                "name": "cardsearch",
                "type": 1,
                "options": [{"type": 3, "name": "cardname", "value": "The Gitrog Monster"}],
            },
        }
    )
    assert isinstance(interaction, ApplicationCommandInteraction)
    assert interaction.data.type is ApplicationCommandType.CHAT_INPUT
    assert isinstance(interaction.data.options, list)
    option = interaction.data.options[0]
    assert option.type is ApplicationCommandOptionType.STRING
    assert option.value == "The Gitrog Monster"
    assert interaction.locale is Locale.ENGLISH_UK
    assert interaction.context is InteractionContextType.GUILD
    assert interaction.authorizing_integration_owners == {
        ApplicationIntegrationType.GUILD_INSTALL: Snowflake(12)
    }
    assert interaction.app_permissions == 442368


def test_component_autocomplete_and_modal_interactions() -> None:
    component = interaction_from(
        {**COMMON, "type": 3, "data": {"custom_id": "yes", "component_type": 2, "id": 4}}
    )
    assert isinstance(component, ComponentInteraction)
    assert component.data.component_type is ComponentType.BUTTON
    autocomplete = interaction_from(
        {
            **COMMON,
            "type": 4,
            "data": {
                "id": "20",
                "name": "card",
                "type": 1,
                "options": [{"type": 3, "name": "name", "value": "Gitr", "focused": True}],
            },
        }
    )
    assert isinstance(autocomplete, AutocompleteInteraction)
    modal = interaction_from(
        {
            **COMMON,
            "type": 5,
            "data": {
                "custom_id": "form",
                "components": [
                    {
                        "type": 18,
                        "id": 1,
                        "component": {"type": 4, "id": 2, "custom_id": "name", "value": "Ada"},
                    }
                ],
            },
        }
    )
    assert isinstance(modal, ModalSubmitInteraction)
    [label] = parse_submitted_components(modal.data.components)
    assert label == SubmittedLabel(id=1, component=SubmittedTextInput(id=2, custom_id="name", value="Ada"))


def test_a_ping_needs_only_its_identity() -> None:
    ping = interaction_from({"id": "1", "application_id": "2", "type": 1, "token": "t", "version": 1})
    assert isinstance(ping, PingInteraction)


def test_an_interaction_type_newer_than_shoal_is_kept() -> None:
    raw: JSONObject = {"id": "1", "application_id": "2", "type": 99, "token": "t", "data": {"new": True}}
    interaction = interaction_from(raw)
    assert isinstance(interaction, UnknownInteraction)
    assert interaction.type == 99
    assert interaction.token == "t"
    assert interaction.data == raw


def test_a_malformed_known_interaction_is_an_error() -> None:
    with pytest.raises(PayloadDecodeError):
        interaction_from({**COMMON, "type": 2, "data": {"name": "missing id and type"}})
    with pytest.raises(PayloadDecodeError):
        interaction_from({"no": "interaction"})
    with pytest.raises(PayloadDecodeError):
        interaction_from({"application_id": "2", "type": 99, "data": {}})  # newer, but no id or token


PING = b'{"id":"1","application_id":"2","type":1,"token":"t","version":1}'


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[]",
        b"null",
        PING + b"x",
        # Valid inside the one-field wrapper parse_interaction decodes through, but not one object.
        PING[:-1] + b'},"value":{"id":"1","application_id":"2","type":1,"token":"u"}',
        b"[" * 100_000 + b"]" * 100_000,
    ],
    ids=["empty", "array", "null", "trailing text", "second object", "deeply nested"],
)
def test_only_exactly_one_interaction_object_parses(body: bytes) -> None:
    with pytest.raises(PayloadDecodeError):
        parse_interaction(body)


def test_dispatch_data_parses_as_it_is() -> None:
    assert isinstance(parse_interaction(msgspec.Raw(PING)), PingInteraction)
    assert isinstance(parse_interaction(PING.decode()), PingInteraction)


def test_responses_carry_their_callback_type() -> None:
    assert msgspec.json.decode(encode_json(PongResponse())) == {"type": 1}
    message = MessageResponse(
        data=InteractionMessage(
            content="hi",
            flags=MessageFlags(ephemeral=True),
            components=[
                ActionRow(components=[Button(style=ButtonStyle.PRIMARY, custom_id="again", label="Again")])
            ],
        )
    )
    assert msgspec.json.decode(encode_json(message)) == {
        "type": 4,
        "data": {
            "content": "hi",
            "flags": 64,
            "components": [
                {"type": 1, "components": [{"type": 2, "style": 1, "label": "Again", "custom_id": "again"}]}
            ],
        },
    }
    assert msgspec.json.decode(encode_json(DeferredMessageResponse())) == {"type": 5}
    ephemeral = DeferredMessageResponse(data=InteractionMessage(flags=MessageFlags(ephemeral=True)))
    assert msgspec.json.decode(encode_json(ephemeral)) == {"type": 5, "data": {"flags": 64}}
    assert msgspec.json.decode(encode_json(DeferredUpdateResponse())) == {"type": 6}
    update = UpdateMessageResponse(data=InteractionMessage(content="edited"))
    assert msgspec.json.decode(encode_json(update)) == {"type": 7, "data": {"content": "edited"}}
    assert msgspec.json.decode(encode_json(LaunchActivityResponse())) == {"type": 12}
    choices = AutocompleteResponse(
        data=AutocompleteChoices(choices=[ApplicationCommandOptionChoice(name="a", value="a")])
    )
    assert msgspec.json.decode(encode_json(choices)) == {
        "type": InteractionCallbackType.APPLICATION_COMMAND_AUTOCOMPLETE_RESULT,
        "data": {"choices": [{"name": "a", "value": "a"}]},
    }
    modal = ModalResponse(
        data=Modal(
            custom_id="form",
            title="Tell us",
            components=[
                Label(label="Name", component=TextInput(custom_id="name", style=TextInputStyle.SHORT))
            ],
        )
    )
    assert msgspec.json.decode(encode_json(modal)) == {
        "type": 9,
        "data": {
            "custom_id": "form",
            "title": "Tell us",
            "components": [
                {"type": 18, "label": "Name", "component": {"type": 4, "custom_id": "name", "style": 1}}
            ],
        },
    }


def test_the_callback_response_reports_what_was_created() -> None:
    result = decode_json(
        b'{"interaction":{"id":"1","type":2,"response_message_id":"5","response_message_ephemeral":true},'
        b'"resource":{"type":4}}',
        InteractionCallbackResponse,
    )
    assert result.interaction.type is InteractionType.APPLICATION_COMMAND
    assert result.interaction.response_message_id == Snowflake(5)


def test_followups_and_edits_separate_unset_from_null() -> None:
    assert msgspec.json.decode(encode_json(SendFollowupParams(content="later"))) == {"content": "later"}
    assert msgspec.json.decode(encode_json(EditWebhookMessageParams(content=None, components=[]))) == {
        "content": None,
        "components": [],
    }
