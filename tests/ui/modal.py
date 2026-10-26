import asyncio
import logging
from typing import override

import msgspec
import pytest

from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.payloads import TextInputStyle
from shoal.ui.modal import Modal
from shoal.ui.text_input import TextInput
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
    assert repr(form) == "<Feedback title='Feedback' inputs=2>"


def test_each_modal_gets_its_own_inputs() -> None:
    first, second = Feedback(), Feedback()
    assert first.name is not second.name
    assert first.name is not Feedback.name
    assert [item.custom_id for item in first.children] == ["name", "body"]


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
