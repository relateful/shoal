from shoal.models.message import Message
from shoal.models.user import ClientUser, User
from shoal.payloads import Message as MessagePayload
from shoal.payloads import User as UserPayload
from tests.support.models import ALICE, BOB, BOT, World, decoded, message, user

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
DM = {"id": "60", "type": 1, "recipients": [user(ALICE, "alice")]}


def payload(data: object) -> UserPayload:
    return decoded(data, UserPayload)


async def test_names_follow_discords_display_rules() -> None:
    world = World()
    plain = User(world.state, payload(user(ALICE, "alice")))
    named = User(world.state, payload(user(ALICE, "alice", global_name="Alice")))
    legacy = User(world.state, payload(user(ALICE, "alice") | {"discriminator": "1234"}))
    assert (plain.name, plain.display_name, str(plain)) == ("alice", "alice", "alice")
    assert named.display_name == "Alice"
    assert str(legacy) == "alice#1234"
    assert plain.mention == f"<@{ALICE}>"
    assert not plain.bot
    assert not plain.system


async def test_avatars_fall_back_to_the_default() -> None:
    world = World()
    without = User(world.state, payload(user(ALICE, "alice")))
    with_avatar = User(world.state, payload(user(ALICE, "alice", avatar="a_hash")))
    assert without.avatar is None
    assert without.display_avatar == without.default_avatar
    assert with_avatar.avatar is not None
    assert with_avatar.display_avatar.url.endswith(f"/avatars/{ALICE}/a_hash.webp?animated=true")


async def test_profile_extras_are_none_until_discord_sends_them() -> None:
    world = World()
    plain = User(world.state, payload(user(ALICE, "alice")))
    full = User(
        world.state, payload(user(ALICE, "alice") | {"banner": "b", "accent_color": 7, "public_flags": 4})
    )
    assert plain.banner is None
    assert plain.accent_colour is None
    assert int(plain.public_flags) == 0
    assert full.banner is not None
    assert full.accent_color == 7
    assert int(full.public_flags) == 4


async def test_mentioned_in_checks_mentions_and_everyone() -> None:
    world = World()
    alice = User(world.state, payload(user(ALICE, "alice")))
    mentioning = Message(world.state, decoded(message(1, mentions=[user(ALICE, "alice")]), MessagePayload))
    everyone = Message(world.state, decoded(message(2, mention_everyone=True), MessagePayload))
    neither = Message(world.state, decoded(message(3), MessagePayload))
    assert alice.mentioned_in(mentioning)
    assert alice.mentioned_in(everyone)
    assert not alice.mentioned_in(neither)


async def test_sending_to_a_user_opens_a_dm_first() -> None:
    world = World()
    alice = User(world.state, payload(user(ALICE, "alice")))
    world.transport.queue(200, DM)
    world.transport.queue(200, message(9, channel_id=60))
    sent = await alice.send("hi")
    assert world.requests() == [
        ("POST", "/users/@me/channels", {"recipient_id": str(ALICE)}),
        ("POST", "/channels/60/messages", {"content": "hi"}),
    ]
    assert sent.guild_id is None


async def test_cached_users_are_found_by_id() -> None:
    world = await World.started()
    found = User.from_cache(world.state, BOB)
    assert found is not None
    assert found.name == "bob"
    assert User.from_cache(world.state, 999) is None


async def test_the_bot_can_edit_itself() -> None:
    world = World()
    me = ClientUser(world.state, payload(user(BOT, "shoalbot") | {"verified": True, "mfa_enabled": False}))
    assert me.verified
    assert not me.mfa_enabled
    world.transport.queue(200, user(BOT, "renamed"))
    edited = await me.edit(username="renamed", avatar=PNG, banner=None)
    method, path, _ = world.last_request()
    assert (method, path) == ("PATCH", "/users/@me")
    body = world.last_body()
    assert body["username"] == "renamed"
    assert body["banner"] is None
    assert str(body["avatar"]).startswith("data:image/png;base64,")
    assert edited is me
    assert me.name == "renamed"
    assert repr(edited) == f"<ClientUser id={BOT} name='renamed'>"
