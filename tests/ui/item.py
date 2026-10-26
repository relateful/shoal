import pytest

from shoal.ui.item import InteractiveItem, Item, random_custom_id
from tests.support.client import started
from tests.support.interactions import command, payload


def test_random_custom_ids_are_unique_hex() -> None:
    ids = {random_custom_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(len(found) == 32 and int(found, 16) >= 0 for found in ids)


def test_a_bare_item_cannot_be_rendered() -> None:
    with pytest.raises(NotImplementedError):
        Item().to_component()


async def test_the_default_callback_does_nothing() -> None:
    client, _ = await started()
    interaction = await client.process_interaction(payload(command("x")))
    item = InteractiveItem(custom_id="x")
    item.refresh(interaction, [], None)
    await item.invoke(interaction)
    assert item.is_persistent()
    assert item.is_dispatchable()
