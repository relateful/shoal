import msgspec
import pytest

from shoal.client.interaction import Interaction
from shoal.core.codec import encode_json
from shoal.payloads import MenuActionItemStyle
from shoal.ui.action_row import ActionRow
from shoal.ui.button import Button
from shoal.ui.content import TextDisplay
from shoal.ui.item import Item
from shoal.ui.layout import Container, Section
from shoal.ui.overflow import MenuActionItem, OverflowMenu, OverflowMenuGroup
from shoal.ui.view import LayoutView, View
from tests.support.calls import call_unchecked
from tests.support.client import started
from tests.support.fakes import settle
from tests.support.interactions import component, payload


def parent_of(item: Item) -> Item | None:
    """Read through a function, so the checkers do not narrow `parent` across calls."""
    return item.parent


def encoded(item: OverflowMenu) -> object:
    return msgspec.json.decode(encode_json(item.to_component()))


def test_a_menu_encodes_its_groups_and_actions() -> None:
    menu = OverflowMenu(
        OverflowMenuGroup(
            MenuActionItem(label="Close", custom_id="close", style=MenuActionItemStyle.DANGER, emoji="🔒"),
            label="Manage",
        ),
        id=5,
    )
    docs = menu.add_action(label="Docs", url="https://example.com", description="Read first")
    assert docs.style is MenuActionItemStyle.LINK
    assert not docs.is_dispatchable()
    assert docs.is_persistent()
    assert encoded(menu) == {
        "type": 25,
        "id": 5,
        "groups": [
            {
                "label": "Manage",
                "components": [
                    {"type": 26, "custom_id": "close", "label": "Close", "style": 2, "emoji": {"name": "🔒"}},
                    {
                        "type": 26,
                        "label": "Docs",
                        "style": 3,
                        "description": "Read first",
                        "url": "https://example.com",
                    },
                ],
            }
        ],
    }
    assert menu.count() == 3
    assert "Close" in repr(menu.children[0])
    assert "groups=1" in repr(menu)
    assert "Manage" in repr(menu.groups[0])


def test_add_action_starts_a_group_when_there_is_none() -> None:
    menu = OverflowMenu()
    menu.add_action(label="Pin")
    assert len(menu.groups) == 1
    assert menu.groups[0].label is None


def test_a_link_action_cannot_have_a_custom_id() -> None:
    with pytest.raises(ValueError, match="link action"):
        MenuActionItem(label="x", url="https://example.com", custom_id="x")


def test_groups_and_menus_refuse_other_things() -> None:
    with pytest.raises(TypeError, match="menu action items"):
        call_unchecked(OverflowMenuGroup().add_item, Button())
    with pytest.raises(TypeError, match="holds groups"):
        call_unchecked(OverflowMenu().add_group, Button())


def test_a_group_belongs_to_one_menu() -> None:
    group = OverflowMenuGroup()
    menu = OverflowMenu(group)
    menu.add_group(group)
    assert menu.groups == [group]
    with pytest.raises(ValueError, match="already belongs"):
        OverflowMenu(group)
    menu.remove_group(group).remove_group(OverflowMenuGroup())
    assert group.menu is None
    OverflowMenu(group)


def test_actions_follow_their_group_in_and_out_of_the_menu() -> None:
    first, second = MenuActionItem(label="a"), MenuActionItem(label="b")
    group = OverflowMenuGroup(first)
    menu = OverflowMenu(group)
    assert parent_of(first) is menu
    group.add_item(second)
    assert parent_of(second) is menu
    assert menu.children == [first, second]
    group.remove_item(first).remove_item(MenuActionItem(label="c"))
    assert parent_of(first) is None
    group.clear_items()
    assert parent_of(second) is None
    loose = OverflowMenuGroup(first)
    assert parent_of(first) is None
    menu.add_group(loose)
    menu.remove_group(loose)
    assert parent_of(first) is None


def test_menus_go_in_rows_and_sections_but_not_legacy_views() -> None:
    row = ActionRow(Button(), OverflowMenu(), Button(), Button(), Button())
    with pytest.raises(ValueError, match="no room"):
        row.add_item(OverflowMenu())
    section = Section("Ticket", accessory=OverflowMenu())
    assert isinstance(section.accessory, OverflowMenu)
    with pytest.raises(TypeError, match="buttons and selects"):
        call_unchecked(View().add_item, OverflowMenu())
    with pytest.raises(TypeError, match="buttons, selects and overflow menus"):
        call_unchecked(ActionRow().add_item, TextDisplay("x"))


def test_a_row_with_a_menu_needs_components_v2() -> None:
    view = LayoutView()
    view.add_item(ActionRow(OverflowMenu(OverflowMenuGroup(MenuActionItem(label="a")))))
    assert view.has_components_v2()


class Ticket(LayoutView):
    """Actions decorated through a group declared on the view: `self` is the view."""

    manage = OverflowMenuGroup(label="Manage")
    summary = Section("Ticket #12", accessory=OverflowMenu(manage))

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.used: list[str] = []

    @manage.action(label="Close", custom_id="ticket:close", style=MenuActionItemStyle.DANGER)
    async def close(self, interaction: Interaction, item: MenuActionItem) -> None:
        del interaction
        self.used.append(item.custom_id)


class Moderation(OverflowMenuGroup):
    """A group subclass declaring its own action: `self` is the group."""

    def __init__(self) -> None:
        super().__init__(label="Moderation")
        self.warned = 0
        self.action(label="Warn", custom_id="mod:warn")(Moderation.warn)

    async def warn(self, interaction: Interaction, item: MenuActionItem) -> None:
        del interaction, item
        self.warned += 1


async def test_actions_decorated_through_a_group_run_on_their_owner() -> None:
    client, _ = await started()
    view = Ticket()
    moderation = Moderation()
    view.add_item(Container(ActionRow(OverflowMenu(moderation))))
    client.add_view(view)
    assert view.is_persistent()
    await client.process_interaction(payload(component("ticket:close")))
    await client.process_interaction(payload(component("mod:warn")))
    await settle()
    assert view.used == ["ticket:close"]
    assert moderation.warned == 1


def test_each_view_gets_its_own_actions_and_the_template_stays_empty() -> None:
    first, second = Ticket(), Ticket()
    assert first.manage is not second.manage
    assert Ticket.manage.items == []
    assert [item.label for item in first.manage.items] == ["Close"]
    assert first.manage.items[0] is not second.manage.items[0]


def test_a_group_added_to_a_menu_already_in_a_view_binds_its_actions() -> None:
    view = Ticket()
    group = OverflowMenuGroup()

    @group.action(label="Late")
    async def late(owner: object, interaction: Interaction, item: MenuActionItem) -> None:
        del owner, interaction, item

    menu = view.summary.accessory
    assert isinstance(menu, OverflowMenu)
    with pytest.raises(TypeError, match="is not a method of the item"):
        menu.add_group(group)
    assert group not in menu.groups
    assert group.menu is None
    assert group.items == []


def test_a_link_action_needs_a_url() -> None:
    with pytest.raises(ValueError, match="needs a url"):
        MenuActionItem(label="x", style=MenuActionItemStyle.LINK).validate()
    MenuActionItem(label="x", url="https://example.com").validate()
