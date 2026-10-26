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
