import pytest

from shoal.models.asset import Asset

CDN = "https://cdn.discordapp.com"


def test_static_images_are_png_and_animated_ones_animated_webp() -> None:
    assert Asset.for_avatar(1, "abc").url == f"{CDN}/avatars/1/abc.png"
    animated = Asset.for_avatar(1, "a_abc")
    assert animated.is_animated()
    assert animated.url == f"{CDN}/avatars/1/a_abc.webp?animated=true"
    assert animated.with_format("gif").url == f"{CDN}/avatars/1/a_abc.gif"


def test_sizes_are_powers_of_two_within_the_cdn_range() -> None:
    icon = Asset.for_guild_icon(2, "icon")
    assert icon.with_size(256).url == f"{CDN}/icons/2/icon.png?size=256"
    assert Asset.for_avatar(1, "a_x").with_size(64).url == f"{CDN}/avatars/1/a_x.webp?size=64&animated=true"
    for size in (8, 100, 8192):
        with pytest.raises(ValueError, match="power of two"):
            icon.with_size(size)


def test_static_images_cannot_be_gifs() -> None:
    with pytest.raises(ValueError, match="animated"):
        Asset.for_guild_icon(2, "icon").with_format("gif")
    animated = Asset.for_guild_icon(2, "a_icon")
    assert animated.with_static_format("jpg") is animated
    assert Asset.for_guild_icon(2, "icon").with_static_format("jpg").url == f"{CDN}/icons/2/icon.jpg"


@pytest.mark.parametrize(
    ("user_id", "discriminator", "index"),
    [((5 << 22) + 3, "0", 5), ((7 << 22), "0", 1), (1, "1337", 2)],
    ids=["new username system", "wraps at six", "legacy discriminator"],
)
def test_default_avatars_follow_discords_index_rules(user_id: int, discriminator: str, index: int) -> None:
    avatar = Asset.for_default_avatar(user_id, discriminator)
    assert avatar.url == f"{CDN}/embed/avatars/{index}.png"
    # The default avatar endpoint ignores sizes, so none is sent.
    assert avatar.with_size(128).url == avatar.url


def test_every_cdn_path() -> None:
    assert Asset.for_member_avatar(2, 1, "h").url == f"{CDN}/guilds/2/users/1/avatars/h.png"
    assert Asset.for_member_banner(2, 1, "h").url == f"{CDN}/guilds/2/users/1/banners/h.png"
    assert Asset.for_banner(1, "h").url == f"{CDN}/banners/1/h.png"
    assert Asset.for_guild_splash(2, "h").url == f"{CDN}/splashes/2/h.png"
    assert Asset.for_discovery_splash(2, "h").url == f"{CDN}/discovery-splashes/2/h.png"
    assert Asset.for_role_icon(3, "h").url == f"{CDN}/role-icons/3/h.png"
    assert Asset.for_emoji(4).url == f"{CDN}/emojis/4.webp"
    assert Asset.for_emoji(4, animated=True).url == f"{CDN}/emojis/4.webp?animated=true"
    assert Asset.for_scheduled_event_cover(5, "h").url == f"{CDN}/guild-events/5/h.png"


def test_assets_compare_and_print_as_their_url() -> None:
    first, second = Asset.for_avatar(1, "abc"), Asset.for_avatar(1, "abc")
    assert first == second
    assert hash(first) == hash(second)
    assert first != first.with_size(32)
    assert str(first) == first.url
    assert first.key == "abc"
    assert repr(first) == f"<Asset url={first.url!r}>"
