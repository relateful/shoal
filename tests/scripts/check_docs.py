import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
check_docs = importlib.import_module("check_docs")

ROUTE_LINE = '<Route method="GET">/channels/[\\{channel.id\\}](/x)/messages/[\\{message.id\\}](/y)</Route>'
PAGE = f"""
import {{ManualAnchor}} from '/snippets/manualanchor.jsx'

### Message Object

###### Message Structure

<ManualAnchor id="create-message-json/form-params" />
###### JSON/Form Params

```python
# Not A Heading
```

## Get Channel Message
{ROUTE_LINE}
"""
DOCS = "https://docs.discord.com/developers/resources/message#get-channel-message"
MISSING = "https://docs.discord.com/developers/resources/message#no-such-section"


def test_slugs_match_the_docs_site() -> None:
    assert check_docs.slugify("Get Guild Member") == "get-guild-member"
    assert check_docs.slugify("`Message` [Object](/x)") == "message-object"


def test_paths_use_shoal_placeholders() -> None:
    raw = "/guilds/[\\{guild.id\\}](/developers/resources/guild#guild-object)/members/[\\{user.id\\}](/x)"
    assert check_docs.normalize_path(raw) == "/guilds/{guild_id}/members/{user_id}"


def test_parse_page_finds_anchors_and_routes() -> None:
    page = check_docs.parse_page("resources/message", PAGE)
    expected = {"message-object", "message-object-message-structure", "create-message-json/form-params"}
    assert expected <= page.anchors
    assert "not-a-heading" not in page.anchors
    [route] = page.routes
    assert (route.anchor, route.method, route.path) == (
        "get-channel-message",
        "GET",
        "/channels/{channel_id}/messages/{message_id}",
    )
    assert route.title == "Get Channel Message"


def test_route_drift_is_reported() -> None:
    pages = {"resources/message": check_docs.parse_page("resources/message", PAGE)}
    routes = [
        ("GET", "/channels/{channel_id}/messages/{message_id}", DOCS),
        ("POST", "/channels/{channel_id}/messages/{message_id}", DOCS),
        ("GET", "/x", MISSING),
        ("GET", "/y", "not a url"),
    ]
    path = "/channels/{channel_id}/messages/{message_id}"
    assert check_docs.check_routes(pages, routes) == [
        f"POST {path}: the docs declare GET {path}",
        f"GET /x: no <Route> under {MISSING}",
        "GET /y: docs link 'not a url' is not a docs URL",
    ]


def test_coverage_counts_documented_and_implemented_endpoints() -> None:
    pages = {
        "resources/message": check_docs.parse_page("resources/message", PAGE),
        "change-log": check_docs.parse_page("change-log", f"## Bug Fix\n{ROUTE_LINE}\n"),
    }
    report = check_docs.coverage_report(
        pages, [("GET", "/channels/{channel_id}/messages/{message_id}", DOCS)]
    )
    assert "Shoal implements **1 of 1** documented HTTP endpoints." in report
    assert "| yes | [Get Channel Message]" in report
    assert "change-log" not in report
