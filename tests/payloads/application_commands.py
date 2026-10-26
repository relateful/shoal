import msgspec

from shoal.core.codec import decode_json, encode_json
from shoal.core.snowflake import Snowflake
from shoal.payloads import (
    ApplicationCommand,
    ApplicationCommandOption,
    ApplicationCommandOptionChoice,
    ApplicationCommandOptionType,
    ApplicationCommandPermission,
    ApplicationCommandPermissionType,
    ApplicationCommandType,
    CreateGuildCommandParams,
    EditCommandPermissionsParams,
    InteractionContextType,
    Locale,
    OverwriteCommandParams,
    Permissions,
    all_channels_permission_id,
    everyone_permission_id,
)

COMMAND = {
    "id": "1",
    "application_id": "2",
    "name": "birthday",
    "description": "Wish a friend a happy birthday",
    "default_member_permissions": None,
    "version": "3",
    "contexts": [0, 1, 2],
    "name_localizations": {"zh-CN": "生日", "xx-YY": "future locale"},
    "options": [
        {
            "type": 2,
            "name": "settings",
            "description": "Birthday settings",
            "options": [
                {
                    "type": 1,
                    "name": "set",
                    "description": "Set a birthday",
                    "options": [
                        {"type": 4, "name": "age", "description": "Age", "min_value": 1, "max_value": 150},
                        {"type": 10, "name": "weight", "description": "Weight", "min_value": 0.5},
                        {
                            "type": 3,
                            "name": "colour",
                            "description": "Cake colour",
                            "choices": [{"name": "Blue", "value": "blue"}],
                        },
                    ],
                }
            ],
        }
    ],
}


def test_a_command_with_nested_subcommands_decodes() -> None:
    command = decode_json(msgspec.json.encode(COMMAND), ApplicationCommand)
    assert command.default_member_permissions is None
    assert command.contexts == [
        InteractionContextType.GUILD,
        InteractionContextType.BOT_DM,
        InteractionContextType.PRIVATE_CHANNEL,
    ]
    assert isinstance(command.name_localizations, dict)
    assert command.name_localizations[Locale.CHINESE_CHINA] == "生日"
    assert "xx-YY" in command.name_localizations
    assert isinstance(command.options, list)
    group = command.options[0]
    assert group.type is ApplicationCommandOptionType.SUB_COMMAND_GROUP
    assert isinstance(group.options, list)
    subcommand = group.options[0]
    assert isinstance(subcommand.options, list)
    age, weight, colour = subcommand.options
    assert (age.min_value, age.max_value) == (1, 150)
    assert isinstance(age.min_value, int)
    assert isinstance(weight.min_value, float)
    assert colour.choices == [ApplicationCommandOptionChoice(name="Blue", value="blue")]


def test_permissions_travel_as_strings() -> None:
    params = CreateGuildCommandParams(
        name="ban", description="Ban someone", default_member_permissions=Permissions(ban_members=True)
    )
    body = msgspec.json.decode(encode_json(params))
    assert body == {"name": "ban", "description": "Ban someone", "default_member_permissions": "4"}


def test_unset_fields_are_left_out_and_null_is_kept() -> None:
    params = OverwriteCommandParams(name="ping", default_member_permissions=None)
    assert msgspec.json.decode(encode_json(params)) == {"name": "ping", "default_member_permissions": None}


def test_user_and_message_commands_need_no_description() -> None:
    params = OverwriteCommandParams(name="View Stats", type=ApplicationCommandType.USER)
    assert msgspec.json.decode(encode_json(params)) == {"name": "View Stats", "type": 2}


def test_option_choices_keep_their_value_type() -> None:
    option = ApplicationCommandOption(
        type=ApplicationCommandOptionType.INTEGER,
        name="count",
        description="How many",
        choices=[ApplicationCommandOptionChoice(name="One", value=1)],
    )
    decoded = decode_json(encode_json(option), ApplicationCommandOption)
    assert isinstance(decoded.choices, list)
    assert decoded.choices[0].value == 1
    assert isinstance(decoded.choices[0].value, int)


def test_permission_constants_follow_discord() -> None:
    guild_id = 1_000_000
    assert everyone_permission_id(guild_id) == Snowflake(guild_id)
    assert all_channels_permission_id(guild_id) == Snowflake(guild_id - 1)
    params = EditCommandPermissionsParams(
        permissions=[
            ApplicationCommandPermission(
                id=all_channels_permission_id(guild_id),
                type=ApplicationCommandPermissionType.CHANNEL,
                permission=False,
            )
        ]
    )
    assert msgspec.json.decode(encode_json(params)) == {
        "permissions": [{"id": str(guild_id - 1), "type": 3, "permission": False}]
    }
