"""Check Shoal against the Discord docs source, and report API coverage.

Shoal links every type, constant and endpoint to the Discord docs section it implements. This script
reads the docs source (https://github.com/discord/discord-api-docs) and verifies that:

1. every `https://docs.discord.com/developers/...` link in `src/` points at a page that exists and,
   when it has one, an anchor that exists on that page;
2. every `Route` in `shoal.rest.endpoints` has the method and path Discord declares in the `<Route>`
   of the section its `docs` link points at.

With `--coverage FILE` it also writes a Markdown report of every endpoint Discord documents and
whether Shoal implements it; `--check-coverage FILE` fails when that report is out of date.

    git clone --depth 1 https://github.com/discord/discord-api-docs ../discord-api-docs
    uv run python scripts/check_docs.py --docs-repo ../discord-api-docs --coverage docs/coverage.md
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "shoal"
DOCS_BASE = "https://docs.discord.com/developers/"
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
LINK = re.compile(r"https://docs\.discord\.com/developers/([a-z0-9/-]*)(?:#([a-z0-9/_.-]+))?")
MANUAL_ANCHOR = re.compile(r'<ManualAnchor id="([^"]+)"\s*/>')
MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
NOT_REFERENCE_PAGES = frozenset({"change-log"})
"""Pages that mention routes without documenting them (the changelog refers to endpoints elsewhere)."""
PLACEHOLDER = re.compile(r"\\?\{([a-z_]+)\.([a-z_]+)\\?\}")
ROUTE = re.compile(r'<Route method="([A-Z]+)">(.+?)</Route>')
SUBHEADING_LEVEL = 6
"""Discord prefixes the anchors of level 6 headings with the nearest higher heading."""

type ImplementedRoute = tuple[str, str, str]
"""(method, path, docs URL) of a route Shoal declares."""


@dataclass(frozen=True, slots=True)
class DocumentedRoute:
    """One `<Route>` declaration in the docs."""

    page: str
    anchor: str
    title: str
    method: str
    path: str


@dataclass(slots=True)
class DocsPage:
    """The anchors and routes of one docs page."""

    anchors: set[str] = field(default_factory=set[str])
    routes: list[DocumentedRoute] = field(default_factory=list[DocumentedRoute])


def slugify(heading: str) -> str:
    """The anchor Discord's docs site generates for a heading."""
    text = MARKDOWN_LINK.sub(r"\1", heading).replace("`", "").replace("*", "").lower()
    text = re.sub(r"[^a-z0-9 /_-]", "", text)
    return re.sub(r"\s+", "-", text.strip())


def normalize_path(raw: str) -> str:
    r"""`/guilds/[\{guild.id\}](...)/members` becomes `/guilds/{guild_id}/members`."""
    text = MARKDOWN_LINK.sub(r"\1", raw)
    return PLACEHOLDER.sub(lambda match: f"{{{match.group(1)}_{match.group(2)}}}", text).replace("\\", "")


def parse_page(page: str, text: str) -> DocsPage:
    """Collect a page's anchors (headings and manual anchors) and its route declarations."""
    result = DocsPage()
    in_code = False
    parent = ""
    title = ""
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        result.anchors.update(MANUAL_ANCHOR.findall(line))
        heading = HEADING.match(line)
        if heading:
            level, name = len(heading.group(1)), heading.group(2)
            slug = slugify(name)
            result.anchors.add(slug)
            if level == SUBHEADING_LEVEL and parent:
                result.anchors.add(f"{parent}-{slug}")
            else:
                parent = slug
                title = MARKDOWN_LINK.sub(r"\1", name).replace("`", "")
            continue
        result.routes.extend(
            DocumentedRoute(page, parent, title, method, normalize_path(raw_path))
            for method, raw_path in ROUTE.findall(line)
        )
    return result


def load_docs(repository: Path) -> dict[str, DocsPage]:
    """Every docs page under `developers/`, keyed by its URL path (`resources/user`)."""
    base = repository / "developers"
    pages: dict[str, DocsPage] = {}
    for path in sorted(base.rglob("*.mdx")):
        key = path.relative_to(base).with_suffix("").as_posix().removesuffix("/index")
        pages[key] = parse_page(key, path.read_text(encoding="utf-8"))
    return pages


def links_in_source() -> list[tuple[Path, str, str, str | None]]:
    """Every docs link in `src/`: (file, full URL, page, anchor)."""
    return [
        (path, match.group(0), match.group(1).rstrip("/"), match.group(2))
        for path in sorted(SOURCE.rglob("*.py"))
        for match in LINK.finditer(path.read_text(encoding="utf-8"))
    ]


def check_links(pages: dict[str, DocsPage]) -> list[str]:
    """Problems with links that point at missing pages or anchors."""
    problems: list[str] = []
    for path, url, page, anchor in links_in_source():
        where = path.relative_to(ROOT).as_posix()
        if not page:
            continue
        if page not in pages:
            problems.append(f"{where}: {url} -> no docs page {page!r}")
        elif anchor is not None and anchor not in pages[page].anchors:
            problems.append(f"{where}: {url} -> no anchor {anchor!r} on {page}")
    return problems


def implemented_routes() -> list[ImplementedRoute]:
    """Every route Shoal declares in `shoal.rest.endpoints`."""
    sys.path.insert(0, str(SOURCE.parent))
    from shoal.rest.endpoints import ALL_ROUTES  # noqa: PLC0415 - imported after adjusting sys.path

    return [(route.method.value, route.path, route.docs) for route in ALL_ROUTES]


def check_routes(pages: dict[str, DocsPage], routes: list[ImplementedRoute]) -> list[str]:
    """Problems with routes whose method or path differs from the docs section they link to."""
    problems: list[str] = []
    for method, path, docs in routes:
        match = LINK.fullmatch(docs)
        if match is None:
            problems.append(f"{method} {path}: docs link {docs!r} is not a docs URL")
            continue
        page, anchor = match.group(1), match.group(2)
        documented = [route for route in pages.get(page, DocsPage()).routes if route.anchor == anchor]
        if not documented:
            problems.append(f"{method} {path}: no <Route> under {docs}")
        elif not any(route.method == method and route.path == path for route in documented):
            expected = ", ".join(f"{route.method} {route.path}" for route in documented)
            problems.append(f"{method} {path}: the docs declare {expected}")
    return problems


def _is_deprecated(title: str) -> bool:
    """Whether Discord marks an endpoint deprecated in its heading, such as `Pin Message (deprecated)`."""
    return "(deprecated)" in title.lower()


def coverage_report(pages: dict[str, DocsPage], routes: list[ImplementedRoute]) -> str:
    """Markdown listing every documented endpoint and whether Shoal implements it."""
    implemented = {(method, path) for method, path, _ in routes}
    documented = sorted(
        {
            (route.page, route.title, route.method, route.path, route.anchor)
            for name, page in pages.items()
            if name not in NOT_REFERENCE_PAGES
            for route in page.routes
        }
    )
    current_routes = [entry for entry in documented if not _is_deprecated(entry[1])]
    done = sum((method, path) in implemented for _, _, method, path, _ in current_routes)
    skipped = len(documented) - len(current_routes)
    lines = [
        "# Discord API coverage",
        "",
        "Generated by `scripts/check_docs.py` from the Discord docs source. Do not edit by hand.",
        "",
        (
            f"Shoal implements **{done} of {len(current_routes)}** documented HTTP endpoints. The {skipped} "
            "endpoints Discord marks deprecated are left out, in favour of their replacements."
        ),
        "",
    ]
    current = None
    for page, title, method, path, anchor in documented:
        if page != current:
            current = page
            heading = f"## [{page}]({DOCS_BASE}{page})"
            lines += ["", heading, "", "| | Endpoint | Route |", "| --- | --- | --- |"]
        if (method, path) in implemented:
            mark = "yes"
        elif _is_deprecated(title):
            mark = "deprecated"
        else:
            mark = "no"
        lines.append(f"| {mark} | [{title}]({DOCS_BASE}{page}#{anchor}) | `{method} {path}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run the checks; see the module docstring for the options."""
    parser = argparse.ArgumentParser(description="Check Shoal against the Discord docs source.")
    parser.add_argument("--docs-repo", type=Path, required=True, help="a discord-api-docs checkout")
    parser.add_argument("--coverage", type=Path, help="write the coverage report to this file")
    parser.add_argument("--check-coverage", type=Path, help="fail if this coverage report is stale")
    options = parser.parse_args()

    pages = load_docs(options.docs_repo)
    routes = implemented_routes()
    problems = check_links(pages) + check_routes(pages, routes)
    for problem in problems:
        print(problem)
    report = coverage_report(pages, routes)
    if options.coverage is not None:
        options.coverage.write_text(report, encoding="utf-8", newline="\n")
    stale = False
    if options.check_coverage is not None:
        target: Path = options.check_coverage
        stale = not target.exists() or target.read_text(encoding="utf-8") != report
        if stale:
            print(f"{target} is out of date; rerun with --coverage")
    links = len(links_in_source())
    print(f"checked {links} links and {len(routes)} routes: {len(problems)} problems")
    return 1 if problems or stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
