"""JSON objects as Discord sends them, for tests that need a whole payload rather than one field."""

USER: dict[str, object] = {
    "id": "1",
    "username": "bot",
    "discriminator": "0",
    "global_name": None,
    "avatar": None,
}


GUILD: dict[str, object] = {
    "id": "2",
    "name": "g",
    "owner_id": "1",
    "afk_timeout": 0,
    "roles": [],
    "emojis": [],
    "features": [],
    "preferred_locale": "en-US",
    "premium_progress_bar_enabled": False,
    **dict.fromkeys(
        (
            "icon",
            "splash",
            "discovery_splash",
            "afk_channel_id",
            "application_id",
            "system_channel_id",
            "rules_channel_id",
            "vanity_url_code",
            "description",
            "banner",
            "public_updates_channel_id",
            "safety_alerts_channel_id",
        )
    ),
    **dict.fromkeys(
        (
            "verification_level",
            "default_message_notifications",
            "explicit_content_filter",
            "mfa_level",
            "system_channel_flags",
            "premium_tier",
            "nsfw_level",
        ),
        0,
    ),
}


MESSAGE: dict[str, object] = {
    "id": "9",
    "channel_id": "3",
    "author": USER,
    "content": "hi",
    "timestamp": "2024-01-01T00:00:00+00:00",
    "edited_timestamp": None,
    "tts": False,
    "mention_everyone": False,
    "mentions": [],
    "mention_roles": [],
    "attachments": [],
    "embeds": [],
    "pinned": False,
    "type": 0,
}


CHANNEL: dict[str, object] = {"id": "3", "type": 0, "guild_id": "2", "name": "general", "position": 0}
MEMBER: dict[str, object] = {
    "user": USER,
    "roles": [],
    "joined_at": "2024-01-01T00:00:00+00:00",
    "deaf": False,
    "mute": False,
    "flags": 0,
}


THREAD: dict[str, object] = {
    "id": "41771983423143937",
    "type": 11,
    "guild_id": "41771983423143937",
    "name": "don't buy dota-2",
    "last_message_id": "155117677105512449",
    "rate_limit_per_user": 2,
    "owner_id": "41771983423143937",
    "parent_id": "41771983423143937",
    "message_count": 1,
    "member_count": 5,
    "thread_metadata": {
        "archived": False,
        "auto_archive_duration": 1440,
        "archive_timestamp": "2021-04-12T23:40:39.855793+00:00",
        "locked": False,
    },
    "total_message_sent": 1,
}
"""Discord's example thread, in the field table's order."""

THREAD_MEMBER: dict[str, object] = {
    "id": "41771983423143937",
    "user_id": "1",
    "join_timestamp": "2024-01-01T00:00:00+00:00",
    "flags": 0,
    "member": MEMBER,
}

INVITE: dict[str, object] = {
    "type": 0,
    "code": "0vCdhLbwjZZTWZLD",
    "guild": {"id": "2", "name": "g", "features": ["NEWS"], "verification_level": 2},
    "channel": {"id": "3", "type": 0, "name": "general"},
    "inviter": USER,
    "expires_at": "2026-01-02T00:00:00+00:00",
}

INVITE_WITH_METADATA: dict[str, object] = {
    **INVITE,
    "uses": 0,
    "max_uses": 0,
    "max_age": 86400,
    "temporary": False,
    "created_at": "2026-01-01T00:00:00+00:00",
}

REGION: dict[str, object] = {
    "id": "rotterdam",
    "name": "Rotterdam",
    "optimal": True,
    "deprecated": False,
    "custom": False,
}

AUTOMOD_RULE: dict[str, object] = {
    "id": "969707018069872670",
    "guild_id": "613425648685547541",
    "name": "Keyword Filter 1",
    "creator_id": "423457898095789043",
    "event_type": 1,
    "trigger_type": 1,
    "trigger_metadata": {
        "keyword_filter": ["cat*", "*dog", "*ana*", "i like c++"],
        "regex_patterns": ["(b|c)at", "^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$"],
    },
    "actions": [
        {
            "type": 1,
            "metadata": {
                "custom_message": "Please keep financial discussions limited to the #finance channel"
            },
        },
        {"type": 2, "metadata": {"channel_id": "123456789123456789"}},
        {"type": 3, "metadata": {"duration_seconds": 60}},
    ],
    "enabled": True,
    "exempt_roles": ["323456789123456789", "423456789123456789"],
    "exempt_channels": ["523456789123456789"],
}
"""Discord's example, in the field table's order."""

ENTITLEMENT: dict[str, object] = {
    "id": "1019653849998299136",
    "sku_id": "1019475255913222144",
    "application_id": "1019370614521200640",
    "user_id": "771129655544643584",
    "type": 8,
    "deleted": False,
    "starts_at": "2022-09-14T17:00:18.704163+00:00",
    "ends_at": "2022-10-14T17:00:18.704163+00:00",
    "guild_id": "1015034326372454400",
    "consumed": False,
}
"""Discord's example, in the field table's order and without the fields the table leaves out."""

SUBSCRIPTION: dict[str, object] = {
    "id": "1278078770116427839",
    "user_id": "1088605110638227537",
    "sku_ids": ["1158857122189168803"],
    "entitlement_ids": [],
    "renewal_sku_ids": None,
    "current_period_start": "2024-08-27T19:48:44.406602+00:00",
    "current_period_end": "2024-09-27T19:48:44.406602+00:00",
    "status": 0,
    "canceled_at": None,
}
"""Discord's example."""

SCHEDULED_EVENT: dict[str, object] = {
    "id": "40",
    "guild_id": "2",
    "channel_id": None,
    "creator_id": "1",
    "name": "Meetup",
    "description": "Bring snacks",
    "scheduled_start_time": "2026-02-01T18:00:00+00:00",
    "scheduled_end_time": "2026-02-01T20:00:00+00:00",
    "privacy_level": 2,
    "status": 1,
    "entity_type": 3,
    "entity_id": None,
    "entity_metadata": {"location": "Town hall"},
    "creator": USER,
    "user_count": 12,
    "image": None,
    "recurrence_rule": {
        "start": "2026-02-01T18:00:00+00:00",
        "end": None,
        "frequency": 2,
        "interval": 1,
        "by_weekday": [6],
        "by_n_weekday": None,
        "by_month": None,
        "by_month_day": None,
        "by_year_day": None,
        "count": None,
    },
}

GUILD_SOUND: dict[str, object] = {
    "name": "Yay",
    "sound_id": "1106714396018884649",
    "volume": 1,
    "emoji_id": "989193655938064464",
    "emoji_name": None,
    "guild_id": "613425648685547541",
    "available": True,
}
"""Discord's example."""

STAGE_INSTANCE: dict[str, object] = {
    "id": "840647391636226060",
    "guild_id": "197038439483310086",
    "channel_id": "733488538393510049",
    "topic": "Testing Testing, 123",
    "privacy_level": 1,
    "discoverable_disabled": False,
    "guild_scheduled_event_id": "947656305244532806",
}
"""Discord's example."""

GUILD_STICKER: dict[str, object] = {
    "id": "8",
    "name": "party",
    "description": None,
    "tags": "tada",
    "type": 2,
    "format_type": 1,
    "available": True,
    "guild_id": "2",
    "user": USER,
}

INTEGRATION: dict[str, object] = {
    "id": "33",
    "name": "Twitch",
    "type": "twitch",
    "enabled": True,
    "syncing": False,
    "role_id": "5",
    "expire_behavior": 0,
    "expire_grace_period": 7,
    "user": USER,
    "account": {"id": "a1", "name": "streamer"},
    "synced_at": "2024-01-01T00:00:00+00:00",
    "subscriber_count": 12,
    "revoked": False,
}

COMMAND_PERMISSIONS: dict[str, object] = {
    "id": "5",
    "application_id": "7",
    "guild_id": "2",
    "permissions": [{"id": "2", "type": 1, "permission": True}],
}

ROLE: dict[str, object] = {
    "id": "5",
    "name": "mods",
    "color": 0,
    "colors": {"primary_color": 0, "secondary_color": None, "tertiary_color": None},
    "hoist": True,
    "position": 1,
    "permissions": "8",
    "managed": False,
    "mentionable": True,
    "flags": 0,
}

EMOJI: dict[str, object] = {
    "id": "41771983429993937",
    "name": "LUL",
    "roles": ["41771983429993000"],
    "user": USER,
    "require_colons": True,
    "managed": False,
    "animated": False,
    "available": True,
}

VOICE_STATE: dict[str, object] = {
    "guild_id": "2",
    "channel_id": "6",
    "user_id": "1",
    "session_id": "abc",
    "deaf": False,
    "mute": False,
    "self_deaf": False,
    "self_mute": True,
    "self_video": False,
    "suppress": True,
    "request_to_speak_timestamp": None,
}
