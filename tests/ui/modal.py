import asyncio
import logging
from typing import override

import msgspec
import pytest

from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.payloads import CheckboxGroupOption, RadioGroupOption, TextInputStyle
from shoal.ui.content import TextDisplay
from shoal.ui.inputs import Checkbox, CheckboxGroup, FileUpload, RadioGroup
from shoal.ui.label import Label
from shoal.ui.modal import Modal
from shoal.ui.text_input import TextInput
from tests.support.calls import call_unchecked
from tests.support.client import started
from tests.support.interactions import command, common, modal_submit, payload
from tests.support.models import ALICE


class Feedback(Modal, title="Feedback"):
    name = TextInput(label="Name", custom_id="name")
    body = TextInput(label="Your feedback", custom_id="body", style=TextInputStyle.PARAGRAPH, max_length=500)

    def __init__(self) -> None:
        super().__init__(custom_id="feedback")
        self.received: list[tuple[str, str]] = []

    @override
    async def on_submit(self, interaction: Interaction) -> None:
        del interaction
        self.received.append((self.name.value, self.body.value))


def test_a_modal_renders_its_inputs_in_labels() -> None:
    form = Feedback()
    assert form.title == "Feedback"
    assert form.custom_id == "feedback"
    assert msgspec.json.decode(encode_json(form.to_modal())) == {
        "custom_id": "feedback",
        "title": "Feedback",
        "components": [
            {
                "type": 18,
                "label": "Name",
                "component": {"type": 4, "custom_id": "name", "style": 1, "required": True},
            },
            {
                "type": 18,
                "label": "Your feedback",
                "component": {
                    "type": 4,
                    "custom_id": "body",
                    "style": 2,
                    "max_length": 500,
                    "required": True,
                },
            },
        ],
    }
    assert repr(form) == "<Feedback title='Feedback' items=2>"


def test_each_modal_gets_its_own_inputs() -> None:
    first, second = Feedback(), Feedback()
    assert first.name is not second.name
    assert first.name is not Feedback.name
    assert [item.custom_id for item in first.children if isinstance(item, TextInput)] == ["name", "body"]


@pytest.mark.parametrize(
    ("field", "problem"),
    [
        (TextInput(label="x" * 46), "label is 46 characters"),
        (TextInput(label="a", description="x" * 101), "description"),
        (TextInput(label="a", placeholder="x" * 101), "placeholder"),
        (TextInput(label="a", default="x" * 4001), "default"),
        (TextInput(label="a", min_length=10, max_length=5), "min_length"),
        (TextInput(label="a", max_length=4001), "max_length"),
    ],
)
def test_inputs_discord_would_refuse_are_refused_before_showing(field: TextInput, problem: str) -> None:
    form = Modal(title="Form").add_item(field)
    with pytest.raises(ValueError, match=problem):
        form.to_modal()


def test_a_title_longer_than_discord_allows_is_refused() -> None:
    with pytest.raises(ValueError, match="title is 46 characters"):
        Modal(title="x" * 46).to_modal()


def test_a_title_is_required() -> None:
    with pytest.raises(TypeError, match="needs a title"):
        Modal()
    assert Modal(title="Plain").title == "Plain"


def test_a_modal_holds_at_most_five_inputs() -> None:
    form = Modal(title="Big")
    for index in range(5):
        form.add_item(TextInput(label=str(index)))
    with pytest.raises(ValueError, match="at most 5"):
        form.add_item(TextInput(label="six"))
    form.remove_item(form.children[0])
    assert len(form.children) == 4


async def test_a_submission_fills_the_inputs_and_runs_on_submit() -> None:
    client, transport = await started()
    opener = await client.process_interaction(payload(command("feedback")))
    form = Feedback()
    transport.queue(204)
    await opener.response.send_modal(form)
    await client.process_interaction(payload(modal_submit("feedback", name="Ada", body="Great")))
    assert await form.wait() is False
    assert form.received == [("Ada", "Great")]
    assert str(form.name) == "Ada"


async def test_a_slow_on_submit_does_not_hold_up_other_interactions() -> None:
    class Slow(Modal, title="Slow"):
        answer = TextInput(label="Answer", custom_id="answer")

        def __init__(self, release: asyncio.Event) -> None:
            super().__init__(custom_id="slow")
            self.release = release

        @override
        async def on_submit(self, interaction: Interaction) -> None:
            del interaction
            await self.release.wait()

    client, _ = await started()
    release = asyncio.Event()
    slow = Slow(release)
    client.view_store.store_modal(slow, user_id=ALICE)
    await client.process_interaction(payload(modal_submit("slow", answer="x")))
    assert not slow.is_finished()
    release.set()
    assert await slow.wait() is False


async def test_legacy_action_row_submissions_still_fill_the_inputs() -> None:
    client, _ = await started()
    form = Feedback()
    client.view_store.store_modal(form, user_id=ALICE)
    rows = [{"type": 1, "components": [{"type": 4, "id": 2, "custom_id": "name", "value": "Old"}]}]
    legacy = common() | {"type": 5, "data": {"custom_id": "feedback", "components": rows}}
    await client.process_interaction(payload(legacy))
    await form.wait()
    assert form.received == [("Old", "")]


async def test_interaction_check_can_refuse_a_submission() -> None:
    class Strict(Modal, title="Strict"):
        answer = TextInput(label="Answer", custom_id="answer")
        submitted = False

        @override
        async def interaction_check(self, interaction: Interaction) -> bool:
            del interaction
            return False

        @override
        async def on_submit(self, interaction: Interaction) -> None:
            del interaction
            self.submitted = True

    client, _ = await started()
    strict = Strict(custom_id="strict")
    client.view_store.store_modal(strict, user_id=ALICE)
    await client.process_interaction(payload(modal_submit("strict", answer="x")))
    assert await strict.wait() is False
    assert not strict.submitted


async def test_a_failing_on_submit_reaches_on_error(caplog: pytest.LogCaptureFixture) -> None:
    class Broken(Modal, title="Broken"):
        @override
        async def on_submit(self, interaction: Interaction) -> None:
            del interaction
            msg = "boom"
            raise RuntimeError(msg)

    client, _ = await started()
    broken = Broken(custom_id="broken")
    client.view_store.store_modal(broken, user_id=ALICE)
    with caplog.at_level(logging.ERROR, logger="shoal.ui"):
        await client.process_interaction(payload(modal_submit("broken")))
        assert await broken.wait() is False
    assert "on_submit raised" in caplog.text


async def test_a_modal_can_time_out() -> None:
    form = Modal(title="Quick", timeout=0.01)
    form.to_modal()
    assert await form.wait() is True
    form.stop()
    waiting = Modal(title="Slow")
    task = asyncio.create_task(waiting.wait())
    await asyncio.sleep(0)
    waiting.stop()
    assert await task is False


async def test_a_non_modal_interaction_is_ignored() -> None:
    client, _ = await started()
    interaction = await client.process_interaction(payload(command("x")))
    form = Feedback()
    await form.dispatch(interaction)
    assert form.received == []


class Survey(Modal, title="Survey"):
    intro = TextDisplay("Tell us about your order")
    size = Label(
        "Size",
        RadioGroup(
            custom_id="size",
            options=[RadioGroupOption(value="s", label="S"), RadioGroupOption(value="l", label="L")],
        ),
    )
    toppings = Label(
        "Toppings",
        CheckboxGroup(custom_id="toppings", options=[CheckboxGroupOption(value="cheese", label="Cheese")]),
    )
    photo = Label("Photo", FileUpload(custom_id="photo"))
    subscribe = Label("Subscribe", Checkbox(custom_id="subscribe"))

    def __init__(self) -> None:
        super().__init__(custom_id="survey")


def test_a_modal_shows_text_and_labelled_inputs() -> None:
    form = Survey()
    components = msgspec.json.decode(encode_json(form.to_modal()))["components"]
    assert [component["type"] for component in components] == [10, 18, 18, 18, 18]
    assert components[4] == {
        "type": 18,
        "label": "Subscribe",
        "component": {"type": 23, "custom_id": "subscribe"},
    }
    assert form.find_item(99) is None
    assert form.size is not Survey.size


async def test_a_submission_fills_every_kind_of_input() -> None:
    client, transport = await started()
    opener = await client.process_interaction(payload(command("survey")))
    form = Survey()
    transport.queue(204)
    await opener.response.send_modal(form)
    attachment = {
        "id": "70",
        "filename": "pizza.png",
        "size": 3,
        "url": "https://cdn.discordapp.com/pizza.png",
        "proxy_url": "https://media.discordapp.net/pizza.png",
    }
    components = [
        {"type": 10, "id": 1},
        {"type": 18, "id": 2, "component": {"type": 21, "id": 3, "custom_id": "size", "value": "l"}},
        {
            "type": 18,
            "id": 4,
            "component": {"type": 22, "id": 5, "custom_id": "toppings", "values": ["cheese"]},
        },
        {"type": 18, "id": 6, "component": {"type": 19, "id": 7, "custom_id": "photo", "values": ["70"]}},
        {"type": 18, "id": 8, "component": {"type": 23, "id": 9, "custom_id": "subscribe", "value": True}},
    ]
    submission = common() | {
        "type": 5,
        "data": {
            "custom_id": "survey",
            "components": components,
            "resolved": {"attachments": {"70": attachment}},
        },
    }
    await client.process_interaction(payload(submission))
    assert await form.wait() is False
    assert isinstance(form.size.component, RadioGroup)
    assert form.size.component.value == "l"
    assert isinstance(form.toppings.component, CheckboxGroup)
    assert form.toppings.component.values == ["cheese"]
    assert isinstance(form.photo.component, FileUpload)
    assert [file.filename for file in form.photo.component.values] == ["pizza.png"]
    assert isinstance(form.subscribe.component, Checkbox)
    assert form.subscribe.component.value is True


def test_a_modal_refuses_what_discord_would() -> None:
    with pytest.raises(ValueError, match="at most 5 items"):
        Survey().add_item(TextDisplay("one too many"))
    with pytest.raises(ValueError, match="needs a label"):
        Modal(title="x").add_item(TextInput()).to_modal()
    twice = (
        Modal(title="x")
        .add_item(TextInput(label="a", custom_id="same"))
        .add_item(TextInput(label="b", custom_id="same"))
    )
    with pytest.raises(ValueError, match="custom_id 'same'"):
        twice.to_modal()
    with pytest.raises(TypeError, match="put inputs in a"):
        call_unchecked(Modal(title="x").add_item, Checkbox())
