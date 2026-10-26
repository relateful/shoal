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
