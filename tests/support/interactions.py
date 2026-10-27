"""Interaction payloads as Discord sends them in the test guild, and views and modals that record calls."""

from collections.abc import Callable, Collection
from typing import TYPE_CHECKING, override

from shoal.client.views import DispatchableView, SubmittableModal
from shoal.core.codec import encode_json
from shoal.payloads import (
    ActionRow,
    ApplicationCommandInteraction,
    AutocompleteInteraction,
    Button,
    ButtonStyle,
    ComponentInteraction,
    Label,
    MessageComponent,
    Modal,
    ModalSubmitInteraction,
    TextInput,
    TextInputStyle,
    parse_interaction,
)
from tests.support.models import ALICE, APPLICATION, GENERAL, GUILD, member, message

if TYPE_CHECKING:
    from shoal.client.interaction import Interaction, InteractionPayload

type Json = dict[str, object]

TOKEN = "interaction-token"


def payload(data: Json) -> "InteractionPayload":
    """`data` decoded as the interaction it is."""
    parsed = parse_interaction(encode_json(data))
    assert isinstance(
        parsed,
        ApplicationCommandInteraction
        | AutocompleteInteraction
        | ComponentInteraction
        | ModalSubmitInteraction,
    )
    return parsed


def common(interaction_id: int = 900, *, in_guild: bool = True) -> Json:
    """The fields every interaction has; in the test guild unless `in_guild` is false."""
    data: Json = {
        "id": str(interaction_id),
        "application_id": str(APPLICATION),
        "token": TOKEN,
        "version": 1,
        "app_permissions": "442368",
        "entitlements": [],
        "authorizing_integration_owners": {"0": str(GUILD)},
        "attachment_size_limit": 26214400,
        "locale": "en-GB",
        "channel_id": str(GENERAL),
    }
    if in_guild:
        data["guild_id"] = str(GUILD)
        data["guild_locale"] = "en-US"
        data["member"] = member(ALICE, "alice", nick="Ally") | {"permissions": "2048"}
        data["context"] = 0
    else:
        data["user"] = {
            "id": str(ALICE),
            "username": "alice",
            "discriminator": "0",
            "global_name": None,
            "avatar": None,
        }
        data["context"] = 1
    return data


def command(
    name: str, *options: Json, interaction_id: int = 900, in_guild: bool = True, resolved: Json | None = None
) -> Json:
    """A slash command interaction, with the users, roles and channels its options refer to in `resolved`."""
    data: Json = {"id": "20", "name": name, "type": 1}
    if options:
        data["options"] = list(options)
    if resolved is not None:
        data["resolved"] = resolved
    return common(interaction_id, in_guild=in_guild) | {"type": 2, "data": data}


def option(name: str, value: object, kind: int = 3, *, focused: bool = False) -> Json:
    """A slash command option as Discord sends it: `kind` 3 is a string, 4 an integer.

    `focused` marks the option the user is typing in, for autocomplete.
    """
    data: Json = {"name": name, "type": kind, "value": value}
    if focused:
        data["focused"] = True
    return data


def autocomplete(name: str, *options: Json) -> Json:
    """An autocomplete interaction."""
    return common() | {"type": 4, "data": {"id": "20", "name": name, "type": 1, "options": list(options)}}


def component(custom_id: str, *, message_id: int | None = 77, values: list[str] | None = None) -> Json:
    """A button press (or a select, with `values`) on message `message_id`."""
    data: Json = {"custom_id": custom_id, "component_type": 2 if values is None else 3}
    if values is not None:
        data["values"] = values
    payload = common() | {"type": 3, "data": data}
    if message_id is not None:
        payload["message"] = message(message_id) | {"guild_id": str(GUILD)}
    return payload


def modal_submit(custom_id: str, **values: str) -> Json:
    """A submitted modal whose text inputs held `values`."""
    components = [
        {
            "type": 18,
            "id": index,
            "component": {"type": 4, "id": index + 100, "custom_id": name, "value": value},
        }
        for index, (name, value) in enumerate(values.items(), start=1)
    ]
    return common() | {"type": 5, "data": {"custom_id": custom_id, "components": components}}


class PersistentView(DispatchableView):
    """A view with one button, `persistent:ok`, recording the interactions it receives."""

    def __init__(self, *, persistent: bool = True, custom_id: str = "persistent:ok") -> None:
        self.persistent = persistent
        self.custom_id = custom_id
        self.received: list[tuple[Interaction, str]] = []
        self.finished = False
        self.on_finish: list[Callable[[], object]] = []

    @override
    def to_components(self) -> list[MessageComponent]:
        button = Button(style=ButtonStyle.PRIMARY, custom_id=self.custom_id, label="OK")
        return [ActionRow(components=[button])]

    @override
    def is_dispatchable(self) -> bool:
        return True

    @override
    def custom_ids(self) -> Collection[str]:
        return [self.custom_id]

    @override
    def is_persistent(self) -> bool:
        return self.persistent

    @override
    def is_finished(self) -> bool:
        return self.finished

    def stop(self) -> None:
        """Stop, telling whoever stored it."""
        self.finished = True
        callbacks, self.on_finish = self.on_finish, []
        for callback in callbacks:
            callback()

    @override
    def when_finished(self, callback: Callable[[], object], /) -> None:
        if self.finished:
            callback()
        else:
            self.on_finish.append(callback)

    @override
    async def dispatch(self, interaction: "Interaction", custom_id: str) -> bool:
        self.received.append((interaction, custom_id))
        return True


class RecordingModal(SubmittableModal):
    """A modal with one text input, `name`, recording its submissions."""

    def __init__(self, custom_id: str = "form") -> None:
        self._custom_id = custom_id
        self.submitted: list[Interaction] = []
        self.finished = False
        self.on_finish: list[Callable[[], object]] = []

    @property
    @override
    def custom_id(self) -> str:
        return self._custom_id

    @override
    def to_modal(self) -> Modal:
        field = TextInput(custom_id="name", style=TextInputStyle.SHORT)
        return Modal(
            custom_id=self._custom_id, title="Form", components=[Label(label="Name", component=field)]
        )

    @override
    def is_finished(self) -> bool:
        return self.finished

    @override
    def stop(self) -> None:
        """Stop, telling whoever stored it."""
        self.finished = True
        callbacks, self.on_finish = self.on_finish, []
        for callback in callbacks:
            callback()

    @override
    def when_finished(self, callback: Callable[[], object], /) -> None:
        if self.finished:
            callback()
        else:
            self.on_finish.append(callback)

    @override
    async def dispatch(self, interaction: "Interaction") -> None:
        self.submitted.append(interaction)
        self.stop()
