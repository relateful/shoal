import pytest

from shoal.rest.route import HTTPMethod, Route

DOCS = "https://docs.discord.com/developers/resources/message#create-message"


def test_compile_fills_and_escapes_parameters() -> None:
    route = Route(HTTPMethod.GET, "/channels/{channel_id}/messages/{message_id}", docs=DOCS)
    compiled = route.compile(channel_id=1, message_id="a/b")
    assert compiled.path == "/channels/1/messages/a%2Fb"
    assert compiled.major == "channel_id=1"
    assert compiled.method is HTTPMethod.GET
    assert route.key == "GET /channels/{channel_id}/messages/{message_id}"


def test_major_parameters_are_sorted_and_combined() -> None:
    route = Route(HTTPMethod.POST, "/webhooks/{webhook_id}/{webhook_token}", docs=DOCS)
    assert route.compile(webhook_id=1, webhook_token="t").major == "webhook_id=1:webhook_token=t"


def test_compile_requires_exactly_the_declared_parameters() -> None:
    route = Route(HTTPMethod.GET, "/guilds/{guild_id}", docs=DOCS)
    with pytest.raises(ValueError, match="missing \\['guild_id'\\]"):
        route.compile()
    with pytest.raises(ValueError, match="unexpected \\['extra'\\]"):
        route.compile(guild_id=1, extra=2)


@pytest.mark.parametrize(
    ("path", "docs"),
    [
        ("channels", DOCS),
        ("/x/{Bad}", DOCS),
        ("/x/{a:>3}", DOCS),
        ("/x", "https://discord.com/developers/docs/resources/message#create-message"),
        ("/x", "https://docs.discord.com/developers/resources/message"),
    ],
)
def test_routes_validate_their_declaration(path: str, docs: str) -> None:
    with pytest.raises(ValueError, match="route"):
        Route(HTTPMethod.GET, path, docs=docs)


def test_idempotent_methods() -> None:
    assert HTTPMethod.GET.is_idempotent
    assert HTTPMethod.PUT.is_idempotent
    assert HTTPMethod.DELETE.is_idempotent
    assert not HTTPMethod.POST.is_idempotent
    assert not HTTPMethod.PATCH.is_idempotent


def test_secret_parameters_never_reach_the_display_path() -> None:
    route = Route(
        HTTPMethod.PATCH,
        "/webhooks/{application_id}/{interaction_token}/messages/@original",
        docs="https://docs.discord.com/developers/interactions/receiving-and-responding#edit-original-interaction-response",
    )
    compiled = route.compile(application_id=1, interaction_token="aW50ZXJhY3Rpb24")
    assert compiled.path == "/webhooks/1/aW50ZXJhY3Rpb24/messages/@original"
    assert compiled.display == "/webhooks/1/{interaction_token}/messages/@original"
    assert "aW50ZXJhY3Rpb24" not in compiled.display
    assert "aW50ZXJhY3Rpb24" not in repr(compiled)

    webhook = Route(
        HTTPMethod.GET,
        "/webhooks/{webhook_id}/{webhook_token}",
        docs="https://docs.discord.com/developers/resources/webhook#get-webhook-with-token",
    ).compile(webhook_id=2, webhook_token="c2VjcmV0")
    assert webhook.display == "/webhooks/2/{webhook_token}"
    assert "c2VjcmV0" not in repr(webhook)


def test_routes_without_secrets_display_their_path() -> None:
    compiled = Route(
        HTTPMethod.GET,
        "/users/{user_id}",
        docs="https://docs.discord.com/developers/resources/user#get-user",
    ).compile(user_id=1)
    assert compiled.display == compiled.path == "/users/1"
