"""Select menus: of strings, users, roles, users and roles, or channels; and the `@ui.select` decorator.

    class Pick(ui.View):
        @ui.select(cls=ui.RoleSelect, placeholder="Pick roles", max_values=3)
        async def roles(self, interaction: Interaction, select: ui.RoleSelect) -> None:
            names = ", ".join(role.name for role in select.values)
            await interaction.response.send_message(f"You picked {names}")

Discord: https://docs.discord.com/developers/components/reference#string-select
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import ClassVar, overload, override

from msgspec import UNSET, UnsetType

from shoal.client.interaction import Interaction
from shoal.core.snowflake import Snowflake
from shoal.models.base import unset_if_none
from shoal.models.channel import AnyGuildChannel, DMChannel, channel_from_payload
from shoal.models.emoji import EmojiLike, partial_emoji
from shoal.models.member import Member
from shoal.models.role import Role
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads.channel import ChannelType
from shoal.payloads.components import (
    ACTION_ROW_MAX_BUTTONS,
    SELECT_MAX_OPTIONS,
    SELECT_OPTION_TEXT_MAX_LENGTH,
    SELECT_PLACEHOLDER_MAX_LENGTH,
    SelectDefaultValue,
    SelectOption,
    StringSelect,
)
from shoal.payloads.components import (
    ChannelSelect as ChannelSelectPayload,
)
from shoal.payloads.components import (
    MentionableSelect as MentionableSelectPayload,
)
from shoal.payloads.components import (
    RoleSelect as RoleSelectPayload,
)
from shoal.payloads.components import (
    UserSelect as UserSelectPayload,
)
from shoal.payloads.interactions import ResolvedData
from shoal.ui.item import ITEM_FACTORY, InteractiveItem, check_length

type SelectPayload = (
    StringSelect | UserSelectPayload | RoleSelectPayload | MentionableSelectPayload | ChannelSelectPayload
)
"""A select as Discord takes it."""


class BaseSelect(InteractiveItem):
    """What every select shares: a placeholder, how many choices, and being disabled.

    Discord: https://docs.discord.com/developers/components/reference#string-select
    """

    __slots__ = (
        "_interaction",
        "_resolved",
        "_values",
        "disabled",
        "max_values",
        "min_values",
        "placeholder",
        "required",
    )

    width: ClassVar[int] = ACTION_ROW_MAX_BUTTONS

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        required: bool | None = None,
        row: int | None = None,
        id: int | None = None,
    ) -> None:
        """A select; see the subclasses for what it chooses."""
        super().__init__(custom_id=custom_id, row=row, id=id)
        self.placeholder: str | None = placeholder
        self.min_values: int = min_values
        self.max_values: int = max_values
        self.disabled: bool = disabled
        self.required: bool | None = required
        self._values: list[str] = []
        self._interaction: Interaction | None = None
        self._resolved: ResolvedData | None = None

    @override
    def refresh(self, interaction: Interaction, values: Sequence[str], resolved: ResolvedData | None) -> None:
        self._values = list(values)
        self._interaction = interaction
        self._resolved = resolved

    @override
    def to_component(self) -> SelectPayload:
        """The select as Discord takes it."""
        raise NotImplementedError

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__} custom_id={self.custom_id!r}>"

    @override
    def validate(self) -> None:
        super().validate()
        check_length(self, "placeholder", self.placeholder, SELECT_PLACEHOLDER_MAX_LENGTH)
        if not 0 <= self.min_values <= self.max_values <= SELECT_MAX_OPTIONS or self.max_values < 1:
            msg = (
                f"{self!r}: needs 0 <= min_values <= max_values <= {SELECT_MAX_OPTIONS} and max_values >= 1, "
                f"not {self.min_values} and {self.max_values}"
            )
            raise ValueError(msg)


class Select(BaseSelect):
    """A select of options you choose; `values` holds the chosen options' values.

    Discord: https://docs.discord.com/developers/components/reference#string-select
    """

    __slots__ = ("options",)

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: Sequence[SelectOption] = (),
        disabled: bool = False,
        required: bool | None = None,
        row: int | None = None,
        id: int | None = None,
    ) -> None:
        """A string select with up to 25 `options`."""
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            row=row,
            id=id,
        )
        self.options: list[SelectOption] = list(options)

    @property
    def values(self) -> list[str]:
        """The values of the options chosen in the last interaction."""
        return list(self._values)

    @override
    def validate(self) -> None:
        super().validate()
        if not 1 <= len(self.options) <= SELECT_MAX_OPTIONS:
            msg = f"{self!r}: a select needs 1 to {SELECT_MAX_OPTIONS} options, not {len(self.options)}"
            raise ValueError(msg)
        for option in self.options:
            check_length(self, "an option's label", option.label, SELECT_OPTION_TEXT_MAX_LENGTH)
            check_length(self, "an option's value", option.value, SELECT_OPTION_TEXT_MAX_LENGTH)
            description = option.description if isinstance(option.description, str) else None
            check_length(self, "an option's description", description, SELECT_OPTION_TEXT_MAX_LENGTH)

    def add_option(
        self,
        *,
        label: str,
        value: str | None = None,
        description: str | None = None,
        emoji: EmojiLike | None = None,
        default: bool = False,
    ) -> None:
        """Add an option; its value is its label when not given."""
        self.options.append(
            SelectOption(
                label=label,
                value=value if value is not None else label,
                description=unset_if_none(description),
                emoji=partial_emoji(emoji) if emoji is not None else UNSET,
                default=default or UNSET,
            )
        )

    @override
    def to_component(self) -> StringSelect:
        """The select as Discord takes it."""
        return StringSelect(
            id=unset_if_none(self.id),
            custom_id=self.custom_id,
            options=self.options,
            placeholder=unset_if_none(self.placeholder),
            min_values=self.min_values,
            max_values=self.max_values,
            required=unset_if_none(self.required),
            disabled=self.disabled or UNSET,
        )


def _users(
    interaction: Interaction, ids: Sequence[str], resolved: ResolvedData | None
) -> list[User | Member]:
    found: list[User | Member] = []
    users = resolved.users if resolved is not None and not isinstance(resolved.users, UnsetType) else {}
    members = resolved.members if resolved is not None and not isinstance(resolved.members, UnsetType) else {}
    state = interaction.state
    for raw in ids:
        user_id = Snowflake(raw)
        user = users.get(user_id)
        if user is None:
            continue
        partial = members.get(user_id)
        if partial is not None and interaction.guild_id is not None:
            found.append(Member.from_partial(state, partial, interaction.guild_id, user=user))
        else:
            found.append(User(state, user))
    return found


def _roles(interaction: Interaction, ids: Sequence[str], resolved: ResolvedData | None) -> list[Role]:
    roles = resolved.roles if resolved is not None and not isinstance(resolved.roles, UnsetType) else {}
    guild_id = interaction.guild_id or 0
    return [
        Role(interaction.state, roles[Snowflake(raw)], guild_id) for raw in ids if Snowflake(raw) in roles
    ]


type SelectedChannel = AnyGuildChannel | Thread | DMChannel
"""A channel picked in a channel select (as Discord resolved it: a partial channel)."""


def _channels(
    interaction: Interaction, ids: Sequence[str], resolved: ResolvedData | None
) -> list[SelectedChannel]:
    channels = (
        resolved.channels if resolved is not None and not isinstance(resolved.channels, UnsetType) else {}
    )
    found: list[SelectedChannel] = []
    for raw in ids:
        data = channels.get(Snowflake(raw))
        if data is not None:
            found.append(channel_from_payload(interaction.state, data))
    return found


class _ResolvedSelect(BaseSelect):
    """A select whose choices Discord resolves into objects."""

    __slots__ = ("default_values",)

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        required: bool | None = None,
        default_values: Sequence[SelectDefaultValue] = (),
        row: int | None = None,
        id: int | None = None,
    ) -> None:
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            row=row,
            id=id,
        )
        self.default_values: list[SelectDefaultValue] = list(default_values)


class UserSelect(_ResolvedSelect):
    """A select of users; `values` holds members in a guild and users elsewhere.

    Discord: https://docs.discord.com/developers/components/reference#user-select
    """

    __slots__ = ()

    @property
    def values(self) -> list[User | Member]:
        """The users chosen in the last interaction."""
        if self._interaction is None:
            return []
        return _users(self._interaction, self._values, self._resolved)

    @override
    def to_component(self) -> UserSelectPayload:
        """The select as Discord takes it."""
        return UserSelectPayload(
            id=unset_if_none(self.id),
            custom_id=self.custom_id,
            placeholder=unset_if_none(self.placeholder),
            default_values=self.default_values or UNSET,
            min_values=self.min_values,
            max_values=self.max_values,
            required=unset_if_none(self.required),
            disabled=self.disabled or UNSET,
        )


class RoleSelect(_ResolvedSelect):
    """A select of roles.

    Discord: https://docs.discord.com/developers/components/reference#role-select
    """

    __slots__ = ()

    @property
    def values(self) -> list[Role]:
        """The roles chosen in the last interaction."""
        if self._interaction is None:
            return []
        return _roles(self._interaction, self._values, self._resolved)

    @override
    def to_component(self) -> RoleSelectPayload:
        """The select as Discord takes it."""
        return RoleSelectPayload(
            id=unset_if_none(self.id),
            custom_id=self.custom_id,
            placeholder=unset_if_none(self.placeholder),
            default_values=self.default_values or UNSET,
            min_values=self.min_values,
            max_values=self.max_values,
            required=unset_if_none(self.required),
            disabled=self.disabled or UNSET,
        )


class MentionableSelect(_ResolvedSelect):
    """A select of users and roles.

    Discord: https://docs.discord.com/developers/components/reference#mentionable-select
    """

    __slots__ = ()

    @property
    def values(self) -> list[User | Member | Role]:
        """The users and roles chosen in the last interaction."""
        if self._interaction is None:
            return []
        users: list[User | Member | Role] = [*_users(self._interaction, self._values, self._resolved)]
        return [*users, *_roles(self._interaction, self._values, self._resolved)]

    @override
    def to_component(self) -> MentionableSelectPayload:
        """The select as Discord takes it."""
        return MentionableSelectPayload(
            id=unset_if_none(self.id),
            custom_id=self.custom_id,
            placeholder=unset_if_none(self.placeholder),
            default_values=self.default_values or UNSET,
            min_values=self.min_values,
            max_values=self.max_values,
            required=unset_if_none(self.required),
            disabled=self.disabled or UNSET,
        )


class ChannelSelect(_ResolvedSelect):
    """A select of channels, optionally of some types only.

    Discord: https://docs.discord.com/developers/components/reference#channel-select
    """

    __slots__ = ("channel_types",)

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        channel_types: Sequence[ChannelType] = (),
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        required: bool | None = None,
        default_values: Sequence[SelectDefaultValue] = (),
        row: int | None = None,
        id: int | None = None,
    ) -> None:
        """A channel select, limited to `channel_types` when given."""
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            required=required,
            default_values=default_values,
            row=row,
            id=id,
        )
        self.channel_types: list[ChannelType] = list(channel_types)

    @property
    def values(self) -> list[SelectedChannel]:
        """The channels chosen in the last interaction."""
        if self._interaction is None:
            return []
        return _channels(self._interaction, self._values, self._resolved)

    @override
    def to_component(self) -> ChannelSelectPayload:
        """The select as Discord takes it."""
        return ChannelSelectPayload(
            id=unset_if_none(self.id),
            custom_id=self.custom_id,
            channel_types=self.channel_types or UNSET,
            placeholder=unset_if_none(self.placeholder),
            default_values=self.default_values or UNSET,
            min_values=self.min_values,
            max_values=self.max_values,
            required=unset_if_none(self.required),
            disabled=self.disabled or UNSET,
        )


type AnySelect = Select | UserSelect | RoleSelect | MentionableSelect | ChannelSelect
"""Every select."""
type SelectCallback[O, S: BaseSelect] = Callable[[O, Interaction, S], Awaitable[None]]
"""A method decorated with `@ui.select`, on a view, an action row or a container."""


def select_factory(
    *,
    cls: type[BaseSelect] | None,
    custom_id: str | None,
    placeholder: str | None,
    min_values: int,
    max_values: int,
    options: Sequence[SelectOption],
    channel_types: Sequence[ChannelType],
    disabled: bool,
    row: int | None,
    id: int | None,
) -> Callable[[], BaseSelect]:
    """A function making the select `@ui.select` and `ActionRow.select` describe, once per instance."""
    kind = cls or Select

    def make() -> BaseSelect:
        if issubclass(kind, Select):
            return kind(
                custom_id=custom_id,
                placeholder=placeholder,
                min_values=min_values,
                max_values=max_values,
                options=options,
                disabled=disabled,
                row=row,
                id=id,
            )
        if issubclass(kind, ChannelSelect):
            return kind(
                custom_id=custom_id,
                channel_types=channel_types,
                placeholder=placeholder,
                min_values=min_values,
                max_values=max_values,
                disabled=disabled,
                row=row,
                id=id,
            )
        return kind(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            row=row,
            id=id,
        )

    return make


@overload
def select[O](
    *,
    cls: None = None,
    custom_id: str | None = None,
    placeholder: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    options: Sequence[SelectOption] = (),
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
) -> Callable[[SelectCallback[O, Select]], SelectCallback[O, Select]]: ...
@overload
def select[O, S: BaseSelect](
    *,
    cls: type[S],
    custom_id: str | None = None,
    placeholder: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    options: Sequence[SelectOption] = (),
    channel_types: Sequence[ChannelType] = (),
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
) -> Callable[[SelectCallback[O, S]], SelectCallback[O, S]]: ...
def select(
    *,
    cls: type[BaseSelect] | None = None,
    custom_id: str | None = None,
    placeholder: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    options: Sequence[SelectOption] = (),
    channel_types: Sequence[ChannelType] = (),
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
) -> Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]:
    """Turn a method of a `View` or an `ActionRow` subclass into a select (a string select, or `cls`).

    The method takes `(self, interaction, select)` and runs on each choice. Each instance gets its
    own select.
    """
    make = select_factory(
        cls=cls,
        custom_id=custom_id,
        placeholder=placeholder,
        min_values=min_values,
        max_values=max_values,
        options=options,
        channel_types=channel_types,
        disabled=disabled,
        row=row,
        id=id,
    )

    def decorator(function: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        setattr(function, ITEM_FACTORY, make)
        return function

    return decorator
