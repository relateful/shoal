"""Slash commands, groups and context menus, registered and run by a `CommandTree`.

    tree = app_commands.CommandTree(client)

    @tree.command(description="Ban a member")
    @app_commands.describe(member="Who to ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(interaction: Interaction, member: Member, days: app_commands.Range[int, 0, 7] = 1) -> None:
        await member.ban(delete_message_seconds=days * 86_400)
        await interaction.response.send_message(f"Banned {member}", ephemeral=True)

Discord: https://docs.discord.com/developers/interactions/application-commands
"""

from shoal.app_commands import checks
from shoal.app_commands.commands import (
    AppCommand,
    Check,
    Command,
    CommandCallback,
    ContextMenu,
    ContextMenuCallback,
    ErrorHandler,
    Group,
    Suggester,
    allowed_contexts,
    allowed_installs,
    autocomplete,
    check,
    choices,
    command,
    context_menu,
    default_permissions,
    describe,
    guild_only,
    guilds,
    nsfw,
    rename,
)
from shoal.app_commands.errors import (
    AppCommandError,
    BotMissingPermissionsError,
    CheckFailureError,
    CommandInvokeError,
    CommandNotFoundError,
    CommandOnCooldownError,
    MissingAnyRoleError,
    MissingPermissionsError,
    MissingRoleError,
    NoPrivateMessageError,
    TransformerError,
)
from shoal.app_commands.models import AnyChoice, Choice, Namespace, Range, RangeSpec
from shoal.app_commands.parameters import (
    NO_DESCRIPTION,
    REQUIRED,
    AutocompleteCallback,
    OptionValue,
    Parameter,
)
from shoal.app_commands.tree import CommandTree

__all__ = [
    "NO_DESCRIPTION",
    "REQUIRED",
    "AnyChoice",
    "AppCommand",
    "AppCommandError",
    "AutocompleteCallback",
    "BotMissingPermissionsError",
    "Check",
    "CheckFailureError",
    "Choice",
    "Command",
    "CommandCallback",
    "CommandInvokeError",
    "CommandNotFoundError",
    "CommandOnCooldownError",
    "CommandTree",
    "ContextMenu",
    "ContextMenuCallback",
    "ErrorHandler",
    "Group",
    "MissingAnyRoleError",
    "MissingPermissionsError",
    "MissingRoleError",
    "Namespace",
    "NoPrivateMessageError",
    "OptionValue",
    "Parameter",
    "Range",
    "RangeSpec",
    "Suggester",
    "TransformerError",
    "allowed_contexts",
    "allowed_installs",
    "autocomplete",
    "check",
    "checks",
    "choices",
    "command",
    "context_menu",
    "default_permissions",
    "describe",
    "guild_only",
    "guilds",
    "nsfw",
    "rename",
]
