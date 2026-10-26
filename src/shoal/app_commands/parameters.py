"""Command options from a callback's type hints, and option values back into those types.

    async def ban(interaction, member: Member, reason: str | None = None, days: Range[int, 0, 7] = 1)

becomes a required user option, an optional string option and an optional integer option from 0
to 7, and the callback receives a `Member`, a `str` or `None`, and an `int`.

Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-structure
"""

import builtins
import enum
import types
import typing
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Union, get_args, get_origin, override

from msgspec import UNSET, UnsetType

from shoal.app_commands.errors import TransformerError
from shoal.app_commands.models import AnyChoice, Choice, RangeSpec
from shoal.client.interaction import Interaction
from shoal.core.snowflake import Snowflake
from shoal.models.channel import (
    CategoryChannel,
    ForumChannel,
    GuildChannel,
    MediaChannel,
    StageChannel,
    TextChannel,
    VoiceChannel,
    channel_from_payload,
    resolve_guild_channel,
)
from shoal.models.member import Member
from shoal.models.role import Role
from shoal.models.thread import Thread
from shoal.models.user import User
from shoal.payloads.application_commands import ApplicationCommandOption, ApplicationCommandOptionType
from shoal.payloads.channel import ChannelType
from shoal.payloads.interactions import ResolvedData
from shoal.payloads.message import Attachment

type OptionValue = str | int | float | bool
"""A raw option value as Discord sends it (IDs for users, roles, channels and attachments)."""
type AutocompleteCallback = Callable[[Interaction, str], Awaitable[Sequence[AnyChoice]]]
"""Suggests choices for an option from what the user typed so far."""

_PRIMITIVES: Final[dict[object, ApplicationCommandOptionType]] = {
    str: ApplicationCommandOptionType.STRING,
    int: ApplicationCommandOptionType.INTEGER,
    float: ApplicationCommandOptionType.NUMBER,
    bool: ApplicationCommandOptionType.BOOLEAN,
}
_CHANNEL_TYPES: Final[dict[type, list[ChannelType]]] = {
    TextChannel: [ChannelType.GUILD_TEXT, ChannelType.GUILD_ANNOUNCEMENT],
    VoiceChannel: [ChannelType.GUILD_VOICE],
    StageChannel: [ChannelType.GUILD_STAGE_VOICE],
    CategoryChannel: [ChannelType.GUILD_CATEGORY],
    ForumChannel: [ChannelType.GUILD_FORUM, ChannelType.GUILD_MEDIA],
    MediaChannel: [ChannelType.GUILD_MEDIA],
    Thread: [ChannelType.PUBLIC_THREAD, ChannelType.PRIVATE_THREAD, ChannelType.ANNOUNCEMENT_THREAD],
    GuildChannel: [],
}
"""The channel types each channel class accepts; `GuildChannel` accepts every type."""
_PEOPLE: Final[frozenset[type]] = frozenset({Member, User, Role})
"""The classes a user, role or mentionable option converts to."""


class _Required:
    __slots__ = ()

    @override
    def __repr__(self) -> str:
        return "REQUIRED"


REQUIRED: Final = _Required()
"""The default of a parameter without one: the option is required."""


@dataclass(slots=True)
class Parameter:
    """One option of a command, and how its value reaches the callback.

    Discord: https://docs.discord.com/developers/interactions/application-commands#application-command-object-application-command-option-structure
    """

    name: str
    """The callback's parameter name."""
    type: ApplicationCommandOptionType
    display_name: str = ""
    """The option's name in Discord (`@rename`); the parameter name when not renamed."""
    description: str = "No description given"
    default: object = REQUIRED
    choices: list[AnyChoice] = field(default_factory=list[AnyChoice])
    channel_types: list[ChannelType] = field(default_factory=list[ChannelType])
    channel_classes: tuple[builtins.type, ...] = ()
    """The channel classes the callback accepts; empty means any."""
    min_value: int | float | None = None
    max_value: int | float | None = None
    min_length: int | None = None
    max_length: int | None = None
    autocomplete: AutocompleteCallback | None = None
    accepts_member: bool = False
    accepts_user: bool = False
    pass_choice: bool = False
    """Hand the callback the `Choice` picked rather than its value."""
    enum_class: builtins.type[enum.Enum] | None = None

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name

    @property
    def required(self) -> bool:
        """Whether the user must fill the option in."""
        return self.default is REQUIRED

    def to_option(self) -> ApplicationCommandOption:
        """The option as Discord takes it."""
        string = self.type is ApplicationCommandOptionType.STRING
        return ApplicationCommandOption(
            type=self.type,
            name=self.display_name,
            description=self.description,
            required=True if self.required else UNSET,
            choices=[choice.to_payload() for choice in self.choices] or UNSET,
            channel_types=self.channel_types or UNSET,
            min_value=self.min_value if self.min_value is not None and not string else UNSET,
            max_value=self.max_value if self.max_value is not None and not string else UNSET,
            min_length=self.min_length if self.min_length is not None else UNSET,
            max_length=self.max_length if self.max_length is not None else UNSET,
            autocomplete=True if self.autocomplete is not None else UNSET,
        )

    def convert(self, interaction: Interaction, value: OptionValue, resolved: ResolvedData | None) -> object:
        """`value`, as the callback asked for it.

        Raises:
            TransformerError: The value cannot be what the parameter asks for.
        """
        match self.type:
            case ApplicationCommandOptionType.USER:
                return self._user(interaction, value, resolved)
            case ApplicationCommandOptionType.ROLE:
                return self._role(interaction, value, resolved)
            case ApplicationCommandOptionType.MENTIONABLE:
                roles = resolved.roles if resolved is not None else UNSET
                if not isinstance(roles, UnsetType) and Snowflake(str(value)) in roles:
                    return self._role(interaction, value, resolved)
                return self._user(interaction, value, resolved)
            case ApplicationCommandOptionType.CHANNEL:
                return self._channel(interaction, value, resolved)
            case ApplicationCommandOptionType.ATTACHMENT:
                attachments = resolved.attachments if resolved is not None else UNSET
                found = None if isinstance(attachments, UnsetType) else attachments.get(Snowflake(str(value)))
                if found is None:
                    raise TransformerError(self.display_name, value, "the attachment was not sent")
                return found
            case _:
                return self._primitive(value)

    def _primitive(self, value: OptionValue) -> object:
        if self.enum_class is not None:
            try:
                return self.enum_class(value)
            except ValueError as error:
                raise TransformerError(
                    self.display_name, value, f"not a {self.enum_class.__name__}"
                ) from error
        if self.pass_choice:
            picked = next((choice for choice in self.choices if choice.value == value), None)
            if picked is None:
                raise TransformerError(self.display_name, value, "not one of the choices")
            return picked
        if self.type is ApplicationCommandOptionType.NUMBER and isinstance(value, int):
            return float(value)
        return value

    def _user(
        self, interaction: Interaction, value: OptionValue, resolved: ResolvedData | None
    ) -> User | Member:
        user_id = Snowflake(str(value))
        users = resolved.users if resolved is not None else UNSET
        members = resolved.members if resolved is not None else UNSET
        user = None if isinstance(users, UnsetType) else users.get(user_id)
        if user is None:
            raise TransformerError(self.display_name, value, "the user was not sent")
        partial = None if isinstance(members, UnsetType) else members.get(user_id)
        if self.accepts_member and partial is not None and interaction.guild_id is not None:
            return Member.from_partial(interaction.state, partial, interaction.guild_id, user=user)
        if not self.accepts_user:
            raise TransformerError(self.display_name, value, "the user is not a member of this server")
        return User(interaction.state, user)

    def _role(self, interaction: Interaction, value: OptionValue, resolved: ResolvedData | None) -> Role:
        roles = resolved.roles if resolved is not None else UNSET
        role = None if isinstance(roles, UnsetType) else roles.get(Snowflake(str(value)))
        if role is None or interaction.guild_id is None:
            raise TransformerError(self.display_name, value, "the role was not sent")
        return Role(interaction.state, role, interaction.guild_id)

    def _channel(self, interaction: Interaction, value: OptionValue, resolved: ResolvedData | None) -> object:
        channel_id = Snowflake(str(value))
        channel = resolve_guild_channel(interaction.state, channel_id)
        if channel is None:
            channels = resolved.channels if resolved is not None else UNSET
            partial = None if isinstance(channels, UnsetType) else channels.get(channel_id)
            if partial is None:
                raise TransformerError(self.display_name, value, "the channel was not sent")
            channel = channel_from_payload(interaction.state, partial)
        if self.channel_classes and not isinstance(channel, self.channel_classes):
            raise TransformerError(self.display_name, value, f"not a {_names(self.channel_classes)}")
        return channel


def _names(classes: tuple[type, ...]) -> str:
    return " or ".join(cls.__name__ for cls in classes)


def parameter_from_annotation(name: str, annotation: object, default: object) -> Parameter:
    """The parameter a callback declares as `name: annotation = default`.

    Raises:
        TypeError: The annotation is not something an option can hold.
    """
    spec: RangeSpec | None = None
    if get_origin(annotation) is typing.Annotated:
        annotation, *extras = get_args(annotation)
        spec = next((extra for extra in extras if isinstance(extra, RangeSpec)), None)
    members = _union_members(annotation)
    if type(None) in members:
        members = [member for member in members if member is not type(None)]
        if default is REQUIRED:
            default = None
    parameter = _classify(name, members, default)
    if spec is not None:
        _apply_range(parameter, spec)
    return parameter


def _union_members(annotation: object) -> list[object]:
    if get_origin(annotation) in {Union, types.UnionType}:
        return list(get_args(annotation))
    return [annotation]


def _classify(name: str, members: list[object], default: object) -> Parameter:
    if len(members) == 1:
        single = members[0]
        if single in _PRIMITIVES:
            return Parameter(name=name, type=_PRIMITIVES[single], default=default)
        if get_origin(single) is Literal:
            return _literal(name, get_args(single), default)
        if get_origin(single) is Choice:
            [inner] = get_args(single)
            return Parameter(name=name, type=_PRIMITIVES[inner], default=default, pass_choice=True)
        if isinstance(single, type) and issubclass(single, enum.Enum):
            return _enum(name, single, default)
        if single is Attachment:
            return Parameter(name=name, type=ApplicationCommandOptionType.ATTACHMENT, default=default)
    accepts_member = Member in members
    accepts_user = User in members
    role = Role in members
    channels = tuple(member for member in members if isinstance(member, type) and member in _CHANNEL_TYPES)
    rest = [
        member
        for member in members
        if not (isinstance(member, type) and (member in _PEOPLE or member in _CHANNEL_TYPES))
    ]
    if rest:
        msg = f"parameter {name!r}: {rest[0]!r} cannot be a command option"
        raise TypeError(msg)
    if channels and (accepts_member or accepts_user or role):
        msg = f"parameter {name!r}: an option cannot be both a channel and a user or role"
        raise TypeError(msg)
    if channels:
        kinds = [] if GuildChannel in channels else [kind for cls in channels for kind in _CHANNEL_TYPES[cls]]
        return Parameter(
            name=name,
            type=ApplicationCommandOptionType.CHANNEL,
            default=default,
            channel_types=list(dict.fromkeys(kinds)),
            channel_classes=() if GuildChannel in channels else channels,
        )
    kind = (
        ApplicationCommandOptionType.MENTIONABLE
        if role and (accepts_member or accepts_user)
        else ApplicationCommandOptionType.ROLE
        if role
        else ApplicationCommandOptionType.USER
    )
    return Parameter(
        name=name, type=kind, default=default, accepts_member=accepts_member, accepts_user=accepts_user
    )


def _literal(name: str, values: tuple[object, ...], default: object) -> Parameter:
    kind, choices = _choices(name, [(str(value), value) for value in values])
    return Parameter(name=name, type=kind, default=default, choices=choices)


def _enum(name: str, enum_class: type[enum.Enum], default: object) -> Parameter:
    kind, choices = _choices(name, [(member.name, member.value) for member in enum_class])
    return Parameter(name=name, type=kind, default=default, choices=choices, enum_class=enum_class)


def _choices(
    name: str, pairs: list[tuple[str, object]]
) -> tuple[ApplicationCommandOptionType, list[AnyChoice]]:
    """The option type and choices for labelled values, which must all be str, all int or all float."""
    choices = [_choice(name, label, value) for label, value in pairs]
    kinds = {type(choice.value) for choice in choices}
    if len(kinds) != 1:
        msg = f"parameter {name!r}: the choices need values of one type: str, int or float"
        raise TypeError(msg)
    return _PRIMITIVES[kinds.pop()], choices


def _choice(name: str, label: str, value: object) -> AnyChoice:
    # `bool` is an `int` to isinstance, but Discord has no boolean choices.
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        msg = f"parameter {name!r}: {value!r} cannot be a choice; use str, int or float values"
        raise TypeError(msg)
    if isinstance(value, str):
        return Choice(name=label, value=value)
    if isinstance(value, int):
        return Choice(name=label, value=value)
    return Choice(name=label, value=value)


def _apply_range(parameter: Parameter, spec: RangeSpec) -> None:
    if parameter.type is ApplicationCommandOptionType.STRING:
        parameter.min_length = None if spec.minimum is None else int(spec.minimum)
        parameter.max_length = None if spec.maximum is None else int(spec.maximum)
    else:
        parameter.min_value = spec.minimum
        parameter.max_value = spec.maximum
