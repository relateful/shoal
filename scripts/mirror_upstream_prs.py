"""Open a Shoal pull request for every pull request on Discord's docs that touches the API Shoal models.

Discord's docs source (https://github.com/discord/discord-api-docs) is Shoal's source of truth, and
`discord-api-docs.lock` pins the revision of it that CI checks Shoal against. This script lists the
pull requests opened or updated upstream since the last run and, for each that matters to Shoal,
keeps one pull request here on the branch `upstream/discord-api-docs-<number>`:

1. The branch moves the pin to the upstream change (GitHub's test merge of it into upstream main
   while open, its merge commit once merged) and regenerates `docs/coverage.md` for it, so CI checks
   Shoal against the change.
   The body lists the changed files with links to their diffs and what `scripts/check_docs.py`
   reports against the new revision that it did not against the old one.
2. The changed paths decide whether a change matters, through `RULES`: a page Shoal models gets the
   labels of the areas it feeds (`payloads`, `rest`, `gateway`, ...); a change whose pages a bot
   library has no use for (the Social SDK, Activities, guides, the site's own assets) gets no pull
   request. A path no rule covers, an unrelated page that Shoal links to anyway, or a change to the
   change log alone gets a pull request labelled `needs-triage`, for a person to decide.
3. Later runs act only on what changed upstream since the record at the end of the body: new commits
   move the pin, a merge moves it to the merge commit and says Shoal needs updating, a close without
   merging closes the pull request. A pull request or label a person changed by hand is left alone.
   While a branch holds only the mirror's commits it is rebuilt on `main` whenever `main` moves; once
   someone pushes to it, the mirror only adds commits that move the pin.

GitHub Actions runs it hourly (`.github/workflows/upstream-docs.yml`). To see what it would do, with
the docs check run in a checkout the script may move freely:

    export GITHUB_TOKEN=$(gh auth token)
    uv run python scripts/mirror_upstream_prs.py --since-hours 72 --docs-repo ../docs-mirror --dry-run

`--unmatched DOCS_REPO` lists the files of a docs checkout that no rule covers.
"""

import argparse
import base64
import difflib
import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Protocol, override

import msgspec

from check_docs import DOCS_BASE, check, links_in_source

API = "https://api.github.com"
BRANCH_PREFIX = "upstream/discord-api-docs-"
CHECK_DOCS_COMMAND = (
    "uv run python scripts/check_docs.py --docs-repo ../discord-api-docs --coverage docs/coverage.md"
)
COMMIT_AUTHOR = {"name": "Shoal docs mirror", "email": "upstream-docs-mirror@users.noreply.github.com"}
"""Who the mirror's commits are by; a branch holding only commits by this address is the mirror's."""
CONFLICT_NOTE = (
    "GitHub has no test merge of this change into upstream main (it conflicts), so the pin is its head "
    "commit, which branched from an older main: the docs check can include what upstream changed since "
    "on the same pages."
)
COVERAGE_FILE = "docs/coverage.md"
COVERED_COMMENT = (
    "Merged upstream, and main already pins a revision that includes it, so this has nothing left to "
    "pin. If its branch carries Shoal changes, reopen it, take main's `discord-api-docs.lock` and "
    "`docs/coverage.md`, and merge."
)
DEFAULT_BRANCH = "main"
DEFAULT_REPOSITORY = "relateful/shoal"
FILE_LIST_BUDGET = 30_000
"""Characters of file list in a pull request's body; GitHub caps a body at 65536."""
FOOTER = (
    "<sub>Kept up to date by `scripts/mirror_upstream_prs.py`, which rewrites this body when the upstream "
    "pull request changes; discuss in comments. While this branch holds only the mirror's commits it is "
    "rebuilt on `main`; once you push to it, the mirror only adds commits that move the pin.</sub>"
)
LABEL_MERGED = "upstream-merged"
LABEL_NEEDS_TRIAGE = "needs-triage"
LABEL_TRACKER = "upstream-docs"
LABEL_UNRELATED = "unrelated"
LOCK_FILE = "discord-api-docs.lock"
MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]()!<>|~])")
MARKER = re.compile(r"<!-- upstream-docs-mirror (\{[^\n]*\}) -->\s*\Z")
"""The record at the very end of a pull request's body; anything earlier is upstream text and never read."""
MAX_LOOKBACK = timedelta(days=7)
"""How far back a run looks at most, so a run that keeps failing does not reread ever more."""
MAX_RETRY_DELAY = 300.0
"""The longest wait for a rate limit to reset before the run gives up on a request."""
OPEN_NOTE = (
    "**Upstream is still open.** This previews the change: the check that the pinned revision is on "
    "Discord's main branch fails until upstream merges, and the mirror then moves the pin to the merge "
    "commit. Do not merge before then."
)
REPORT_LINE_LIMIT = 100
"""Lines of each part of the docs check report shown in a body; the rest are counted."""
RETRIES = 3
RETRY_DELAY = 10.0
"""Seconds before retrying a request GitHub failed with a server error."""
RUN_OVERLAP = timedelta(hours=1)
"""How far before the last successful run to look again, so a pull request updated mid-run is not missed."""
TITLE_LIMIT = 256
"""The longest pull request title GitHub accepts."""
UPSTREAM = "discord/discord-api-docs"
UPSTREAM_REFERENCE = re.compile(r"(?<![\w/])#(\d+)\b")
WRITE_PAUSE = 1.0
"""Seconds between writes; GitHub asks integrations to space out requests that create content."""

LABELS: dict[str, tuple[str, str]] = {
    "changelog": ("c5def5", "Upstream: Discord's change log"),
    "gateway": ("1d76db", "Upstream: gateway connection or events"),
    "interactions": ("5319e7", "Upstream: interactions and application commands"),
    LABEL_NEEDS_TRIAGE: ("fbca04", "Upstream: no triage rule decided this; a person should"),
    "payloads": ("0e8a16", "Upstream: a Discord object Shoal models"),
    "rest": ("006b75", "Upstream: an HTTP endpoint, rate limits or errors"),
    "ui": ("bfd4f2", "Upstream: message and modal components"),
    LABEL_UNRELATED: ("cfd3d7", "Upstream: nothing a bot library models"),
    LABEL_TRACKER: ("0052cc", "Mirrors a pull request on discord/discord-api-docs"),
    LABEL_MERGED: ("6f42c1", "The upstream pull request is merged; Shoal may need updating"),
    "voice": ("d4c5f9", "Upstream: voice connections"),
}
"""Every label this script sets: name to (colour, description). Areas are the ones `RULES` name."""


class UpstreamState(StrEnum):
    """Where the upstream pull request stands."""

    CLOSED = "closed"
    MERGED = "merged"
    OPEN = "open"


class Verdict(StrEnum):
    """Whether a change matters to Shoal."""

    NEEDS_TRIAGE = "needs-triage"
    RELATED = "related"
    UNRELATED = "unrelated"


@dataclass(frozen=True, slots=True)
class Rule:
    """What a docs path is about: the areas of Shoal it feeds, or none if a bot library has no use for it."""

    prefix: str
    topic: str
    areas: tuple[str, ...] = ()
    decides: bool = True
    """False for a page that only points at changes made elsewhere (the change log): it adds its area,
    but the other files decide the verdict, and a person does when there are none."""


RULES = (
    Rule(".gitattributes", "repository tooling"),
    Rule(".github/", "repository tooling"),
    Rule(".gitignore", "repository tooling"),
    Rule(".husky/", "repository tooling"),
    Rule(".mintignore", "repository tooling"),
    Rule(".pr.md", "repository tooling"),
    Rule(".vale.ini", "repository tooling"),
    Rule("CODE_OF_CONDUCT.md", "repository policy"),
    Rule("CONTRIBUTING.md", "repository policy"),
    Rule("LICENSE", "repository policy"),
    Rule("README.md", "repository policy"),
    Rule("developers/activities/", "Activities"),
    Rule("developers/bots/", "guides"),
    Rule("developers/change-log", "change log", ("changelog",), decides=False),
    Rule("developers/communities/", "guides"),
    Rule("developers/components/", "components", ("payloads", "ui")),
    Rule("developers/developer-tools/", "Embedded App and Game SDKs"),
    Rule("developers/discord-social-sdk/", "Social SDK"),
    Rule("developers/discovery/", "app discovery"),
    Rule("developers/events/", "events", ("gateway",)),
    Rule("developers/events/gateway", "gateway events", ("gateway", "payloads")),
    Rule("developers/events/webhook-events", "webhook events", ("payloads",)),
    Rule("developers/game-development/", "game development"),
    Rule("developers/gateway/", "privileged intent guides"),
    Rule("developers/guides", "guides"),
    Rule("developers/interactions/", "interactions", ("interactions", "payloads", "rest")),
    Rule("developers/intro.mdx", "guides"),
    Rule("developers/link-previews/", "link previews"),
    Rule("developers/monetization/", "monetization guides"),
    Rule("developers/platform/", "platform overview"),
    Rule("developers/policies/", "policies"),
    Rule("developers/quick-start/", "guides"),
    Rule("developers/reference.mdx", "API reference", ("payloads", "rest")),
    Rule("developers/resources/", "resources", ("payloads", "rest")),
    Rule("developers/rich-presence/", "Rich Presence"),
    Rule("developers/social-commerce/", "social commerce"),
    Rule("developers/social-layer/", "Social SDK"),
    Rule("developers/topics/certified-devices", "certified devices"),
    Rule("developers/topics/oauth2", "OAuth2", ("rest",)),
    Rule("developers/topics/opcodes-and-status-codes", "opcodes and status codes", ("gateway", "rest")),
    Rule("developers/topics/permissions", "permissions", ("payloads",)),
    Rule("developers/topics/rate-limits", "rate limits", ("rest",)),
    Rule("developers/topics/rpc", "RPC"),
    Rule("developers/topics/teams", "teams", ("payloads",)),
    Rule("developers/topics/threads", "threads", ("gateway", "payloads")),
    Rule("developers/topics/voice-connections", "voice connections", ("voice",)),
    Rule("developers/tutorials/", "tutorials"),
    Rule("docs.json", "site navigation"),
    Rule("favicon.png", "site assets"),
    Rule("images/", "site assets"),
    Rule("logo/", "site assets"),
    Rule("package-lock.json", "repository tooling"),
    Rule("package.json", "repository tooling"),
    Rule("resources/discord-social-sdk/", "Social SDK"),
    Rule("scripts/", "repository tooling"),
    Rule("snippets/", "site assets"),
    Rule("styles/", "site assets"),
    Rule("tools/", "repository tooling"),
    Rule("vale/", "repository tooling"),
)
"""Triage rules for upstream paths, alphabetical. The longest matching prefix decides a path."""


class GitHubUser(msgspec.Struct):
    """The author of a pull request."""

    login: str


class Head(msgspec.Struct):
    """The head of a pull request: its branch and commit."""

    sha: str
    ref: str = ""


class PullRequest(msgspec.Struct):
    """The fields of an upstream pull request this script reads."""

    number: int
    title: str
    html_url: str
    state: str
    updated_at: str
    user: GitHubUser
    head: Head
    merged_at: str | None = None
    merge_commit_sha: str | None = None

    @property
    def upstream_state(self) -> UpstreamState:
        """Open, merged, or closed without merging."""
        if self.merged_at is not None:
            return UpstreamState.MERGED
        return UpstreamState.OPEN if self.state == "open" else UpstreamState.CLOSED

    @property
    def updated(self) -> datetime:
        """When anything on the pull request last changed."""
        return datetime.fromisoformat(self.updated_at)

    @property
    def target(self) -> str:
        """The docs revision to pin: the merge commit once merged.

        Before that, GitHub's test merge of the change into upstream main, so the pin does not go back
        to whatever older main the change branched from; the head commit when there is no test merge
        (the change conflicts with main).
        """
        if self.merge_commit_sha is not None and self.upstream_state is not UpstreamState.CLOSED:
            return self.merge_commit_sha
        return self.head.sha


class ChangedFile(msgspec.Struct):
    """One file a pull request changes."""

    filename: str
    status: str
    additions: int
    deletions: int
    previous_filename: str | None = None

    @property
    def paths(self) -> tuple[str, ...]:
        """The file's path, and the one it was renamed from."""
        if self.previous_filename is None:
            return (self.filename,)
        return (self.filename, self.previous_filename)


class Label(msgspec.Struct):
    """A label on a pull request or in a repository."""

    name: str


class ShoalPull(msgspec.Struct):
    """The fields of a Shoal pull request this script reads."""

    number: int
    title: str
    state: str
    head: Head
    labels: list[Label]
    body: str | None = None
    merged_at: str | None = None


class GitObject(msgspec.Struct):
    """A git object GitHub returns: a commit, a tree, or the target of a ref."""

    sha: str


class GitCommit(msgspec.Struct):
    """A commit and its tree."""

    sha: str
    tree: GitObject


class Ref(msgspec.Struct):
    """A branch and the commit it points at."""

    object: GitObject


class Author(msgspec.Struct):
    """Who wrote a commit."""

    email: str


class CommitDetails(msgspec.Struct):
    """A commit's metadata, as a comparison lists it."""

    author: Author


class ComparedCommit(msgspec.Struct):
    """A commit in a comparison."""

    commit: CommitDetails


class Comparison(msgspec.Struct):
    """How two commits relate."""

    status: str
    behind_by: int
    commits: list[ComparedCommit]


class FileContent(msgspec.Struct):
    """A file at a revision, base64 encoded."""

    content: str


class WorkflowRun(msgspec.Struct):
    """One run of a workflow."""

    created_at: str


class WorkflowRuns(msgspec.Struct):
    """A page of workflow runs."""

    workflow_runs: list[WorkflowRun]


class Mirror(msgspec.Struct, frozen=True, omit_defaults=True):
    """What a pull request last recorded about its upstream pull request; `None` until first recorded."""

    pr: int
    head: str | None = None
    state: UpstreamState | None = None
    verdict: Verdict | None = None
    areas: tuple[str, ...] = ()
    pin: str | None = None
    """The docs revision the branch pins."""

    @property
    def labels(self) -> frozenset[str]:
        """The labels this record implies."""
        return labels_for(self.verdict, self.areas, self.state)


@dataclass(frozen=True, slots=True)
class Tracker:
    """A Shoal pull request the mirror keeps, and the record in its body."""

    number: int
    title: str
    body: str
    is_open: bool
    merged: bool
    labels: frozenset[str]
    mirror: Mirror


@dataclass(frozen=True, slots=True)
class Branch:
    """A mirror branch: its head, whether only the mirror has committed to it, and how far `main` is ahead."""

    sha: str
    owned: bool
    behind: int


@dataclass(frozen=True, slots=True)
class DocsCheck:
    """What `scripts/check_docs.py` reports for Shoal against one docs revision."""

    problems: tuple[str, ...]
    coverage: str


@dataclass(frozen=True, slots=True)
class FileTriage:
    """The verdict on one changed path."""

    path: str
    rule: Rule | None
    linked: bool

    @property
    def verdict(self) -> Verdict:
        """Related if a deciding rule names areas; needs triage if none decides or Shoal links the page."""
        if self.rule is None or not self.rule.decides:
            return Verdict.NEEDS_TRIAGE
        if self.rule.areas:
            return Verdict.RELATED
        return Verdict.NEEDS_TRIAGE if self.linked else Verdict.UNRELATED

    @property
    def summary(self) -> str:
        """The verdict in a few words, for the file list."""
        if self.rule is None:
            return "no triage rule covers this path"
        if not self.rule.decides:
            return f"{', '.join(self.rule.areas)} (the other files decide)"
        if self.rule.areas:
            return ", ".join(self.rule.areas)
        if self.linked:
            return f"{self.rule.topic}, but Shoal links this page"
        return f"unrelated ({self.rule.topic})"


@dataclass(frozen=True, slots=True)
class Triage:
    """The verdict on a whole pull request."""

    verdict: Verdict
    areas: tuple[str, ...]
    files: tuple[FileTriage, ...]

    @property
    def topics(self) -> tuple[str, ...]:
        """What the unrelated files are about, for the closing comment."""
        return tuple(sorted({entry.rule.topic for entry in self.files if entry.rule is not None}))


@dataclass(frozen=True, slots=True)
class Skip:
    """An upstream pull request that gets no Shoal pull request, and why."""

    upstream: int
    reason: str

    def describe(self) -> str:
        """One line, for the log and for dry runs."""
        return f"{UPSTREAM}#{self.upstream}: no pull request ({self.reason})"


@dataclass(slots=True)
class Change:
    """What to do to one Shoal pull request: open it (when `pull` is None), then the rest in order."""

    upstream: int
    pull: int | None
    title: str
    body: str
    pin: str | None = None
    """The docs revision to move the branch's pin to, or `None` to leave the branch alone."""
    coverage: str | None = None
    """`docs/coverage.md` for `pin`, committed with it while the branch holds only the mirror's commits."""
    state: str | None = None
    """`"open"` to reopen, `"closed"` to close, `None` to leave as it is."""
    comments: list[str] = field(default_factory=list[str])
    add_labels: list[str] = field(default_factory=list[str])
    remove_labels: list[str] = field(default_factory=list[str])
    edit: bool = True
    """Whether the title or body differ from the pull request's."""

    @property
    def branch(self) -> str:
        """The branch the pull request is opened from."""
        return branch_name(self.upstream)

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing to do."""
        return not (
            self.pin or self.state or self.comments or self.add_labels or self.remove_labels or self.edit
        )

    def describe(self) -> str:
        """One line per action, for the log and for dry runs."""
        target = f"#{self.pull}" if self.pull is not None else "new pull request"
        lines = [f"{UPSTREAM}#{self.upstream} -> {target}: {self.title}"]
        if self.pin is not None:
            lines.append(f"  pin {LOCK_FILE} to {self.pin} on {self.branch}")
        if self.pull is None:
            lines.append("  open")
        elif self.edit:
            lines.append("  update title and body")
        if self.state is not None:
            lines.append("  reopen" if self.state == "open" else "  close")
        lines.extend(f"  comment: {comment.splitlines()[0]}" for comment in self.comments)
        if self.add_labels:
            lines.append(f"  add labels: {', '.join(self.add_labels)}")
        if self.remove_labels:
            lines.append(f"  remove labels: {', '.join(self.remove_labels)}")
        return "\n".join(lines)


def branch_name(upstream: int) -> str:
    """The branch that mirrors an upstream pull request."""
    return f"{BRANCH_PREFIX}{upstream}"


def rule_for(path: str) -> Rule | None:
    """The rule with the longest prefix of `path`, if any."""
    matches = [rule for rule in RULES if path.startswith(rule.prefix)]
    return max(matches, key=lambda rule: len(rule.prefix), default=None)


def triage(files: Iterable[ChangedFile], linked_pages: frozenset[str]) -> Triage:
    """Decide whether a change matters to Shoal from the paths it touches.

    Related when any path feeds an area of Shoal; unrelated when every path is about something a bot
    library has no use for; otherwise (a path no rule covers, a linked page, only the change log, no
    files) a person decides.
    """
    entries = tuple(
        FileTriage(path, rule_for(path), path in linked_pages) for file in files for path in file.paths
    )
    verdicts = {entry.verdict for entry in entries}
    areas = tuple(sorted({area for entry in entries if entry.rule is not None for area in entry.rule.areas}))
    if Verdict.RELATED in verdicts:
        return Triage(Verdict.RELATED, areas, entries)
    if verdicts == {Verdict.UNRELATED}:
        return Triage(Verdict.UNRELATED, (), entries)
    return Triage(Verdict.NEEDS_TRIAGE, areas, entries)


def linked_pages() -> frozenset[str]:
    """The docs source file of every page Shoal links to (`developers/resources/user.mdx`)."""
    return frozenset(f"developers/{page}.mdx" for _, _, page, _ in links_in_source())


def labels_for(verdict: Verdict | None, areas: Iterable[str], state: UpstreamState | None) -> frozenset[str]:
    """The labels a verdict and an upstream state call for, besides `upstream-docs`."""
    if verdict is Verdict.UNRELATED:
        return frozenset({LABEL_UNRELATED})
    labels = set(areas)
    if verdict is Verdict.NEEDS_TRIAGE:
        labels.add(LABEL_NEEDS_TRIAGE)
    if state is UpstreamState.MERGED:
        labels.add(LABEL_MERGED)
    return frozenset(labels)


def upstream_text(text: str) -> str:
    """Someone else's text, made safe to show in markdown: no formatting, links, HTML or mentions."""
    return qualify_references(MARKDOWN_SPECIAL.sub(r"\\\1", text)).replace("@", "&#64;")


def code(text: str) -> str:
    """A path as a code span, or as escaped text when it holds a backtick that would end the span."""
    return f"`{text}`" if "`" not in text else upstream_text(text)


def qualify_references(text: str) -> str:
    """Point `#123` at the upstream repository, so it does not link an unrelated Shoal issue."""
    return UPSTREAM_REFERENCE.sub(rf"{UPSTREAM}#\1", text)


def tracker_title(pull: PullRequest) -> str:
    """The pull request's title: the upstream number and title, cut to the length GitHub accepts."""
    title = f"docs#{pull.number}: {qualify_references(pull.title)}"
    return title if len(title) <= TITLE_LIMIT else title[: TITLE_LIMIT - 1] + "…"


def file_anchor(pull: PullRequest, path: str) -> str:
    """The link to one file's diff on the pull request's "Files changed" tab."""
    return f"{pull.html_url}/files#diff-{hashlib.sha256(path.encode()).hexdigest()}"


def touched_pages(files: Iterable[ChangedFile]) -> frozenset[str]:
    """The docs URL of every page a change touches (`https://docs.discord.com/developers/resources/user`)."""
    return frozenset(
        f"{DOCS_BASE}{path.removeprefix('developers/').removesuffix('.mdx')}"
        for file in files
        for path in file.paths
        if path.startswith("developers/") and path.endswith(".mdx")
    )


def capped(lines: list[str]) -> list[str]:
    """At most `REPORT_LINE_LIMIT` lines, counting the rest."""
    if len(lines) <= REPORT_LINE_LIMIT:
        return lines
    return [*lines[:REPORT_LINE_LIMIT], f"... and {len(lines) - REPORT_LINE_LIMIT} more"]


def on(line: str, pages: frozenset[str]) -> bool:
    """Whether a report line is about one of `pages` (docs URLs without an anchor)."""
    return any(re.search(rf"{re.escape(page)}(?![\w/-])", line) for page in pages)


def render_report(base: DocsCheck, target: DocsCheck, base_pin: str, pin: str, pages: frozenset[str]) -> str:
    """What `scripts/check_docs.py` says about Shoal against `pin` that it did not against `base_pin`.

    Problems and coverage rows are limited to the pages the upstream change touches, so changes
    upstream made elsewhere between the two revisions do not crowd them out.
    """
    lines = [f"### Docs check: `{base_pin[:12]}` to `{pin[:12]}`", ""]
    new = [problem for problem in target.problems if problem not in base.problems and on(problem, pages)]
    fixed = [problem for problem in base.problems if problem not in target.problems and on(problem, pages)]
    rows = [
        line
        for line in difflib.unified_diff(base.coverage.splitlines(), target.coverage.splitlines(), n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---")) and on(line, pages)
    ]
    if not (new or fixed or rows):
        return "\n".join([*lines, "No change to the links, routes, events or endpoints Shoal checks."])
    if new:
        lines += [
            f"Problems Shoal now has ({len(new)}):",
            "",
            *(f"- {problem}" for problem in capped(new)),
            "",
        ]
    if fixed:
        lines += [
            f"Problems now gone ({len(fixed)}):",
            "",
            *(f"- {problem}" for problem in capped(fixed)),
            "",
        ]
    if rows:
        lines += ["Coverage changes on the pages this touches:", "", "```diff", *capped(rows), "```"]
    return "\n".join(lines).rstrip()


def fetch_commands(pin: str) -> list[str]:
    """Shell lines that check Shoal against a docs revision."""
    return [
        "```bash",
        "git init ../discord-api-docs",
        f"git -C ../discord-api-docs fetch --depth 1 https://github.com/{UPSTREAM} {pin}",
        "git -C ../discord-api-docs checkout --detach FETCH_HEAD",
        CHECK_DOCS_COMMAND,
        "```",
    ]


def render_body(
    pull: PullRequest, files: list[ChangedFile], result: Triage, mirror: Mirror, report: str | None
) -> str:
    """The pull request's body, ending with the marker that records `mirror`."""
    upstream_state = pull.upstream_state
    verdict = {
        Verdict.NEEDS_TRIAGE: "needs triage: no rule decides every path, so a person should",
        Verdict.RELATED: f"related: {', '.join(result.areas)}",
        Verdict.UNRELATED: f"unrelated: {', '.join(result.topics)}",
    }[result.verdict]
    author = f"[{pull.user.login}](https://github.com/{pull.user.login})"
    pin = mirror.pin or pull.target
    lines = [
        f"Mirrors [{UPSTREAM}#{pull.number}]({pull.html_url}): **{upstream_text(pull.title)}** by {author}.",
        "",
        f"- Triage: {verdict}",
        (
            f"- Pins `{LOCK_FILE}` to [`{pin[:12]}`](https://github.com/{UPSTREAM}/commit/{pin}), so CI "
            "checks Shoal against it"
        ),
        f"- Diff: [files changed]({pull.html_url}/files), [raw diff]({pull.html_url}.diff)",
        "",
    ]
    if upstream_state is UpstreamState.OPEN:
        lines.append(OPEN_NOTE)
        if pull.merge_commit_sha is None:
            lines += ["", CONFLICT_NOTE]
    elif upstream_state is UpstreamState.MERGED:
        lines += [
            "**Merged upstream.** Update Shoal on this branch until CI passes, then merge. To check locally:",
            "",
            *fetch_commands(pin),
        ]
    else:
        lines += ["**Closed upstream without merging**, so there is nothing to update."]
    lines += ["", report or "### Docs check\n\nNot run: the mirror had no docs checkout.", ""]
    lines += [f"### Changed files ({len(files)})", ""]
    by_path = {entry.path: entry for entry in result.files}
    budget = FILE_LIST_BUDGET
    for listed, file in enumerate(files):
        renamed = f" from {code(file.previous_filename)}" if file.previous_filename is not None else ""
        line = (
            f"- [{code(file.filename)}]({file_anchor(pull, file.filename)}) {file.status}{renamed} "
            f"(+{file.additions} -{file.deletions}): {by_path[file.filename].summary}"
        )
        budget -= len(line) + 1
        if budget < 0:
            lines.append(f"- and {len(files) - listed} more on the upstream pull request")
            break
        lines.append(line)
    lines += ["", FOOTER, marker(mirror)]
    return "\n".join(lines)


def marker(mirror: Mirror) -> str:
    """The hidden comment that records `mirror` in a pull request's body."""
    return f"<!-- upstream-docs-mirror {msgspec.json.encode(mirror).decode()} -->"


def unrelated_comment(result: Triage) -> str:
    """Why a mirrored pull request is closed once its upstream change no longer matters to Shoal."""
    return (
        f"Closing as unrelated: every changed file is now about {', '.join(result.topics)}, which Shoal does "
        f"not model. If that is wrong, reopen this and remove the `{LABEL_UNRELATED}` label; the mirror "
        "will not close it again unless the upstream files change."
    )


def merged_comment(pin: str) -> str:
    """What to do once the upstream change is merged."""
    return "\n".join(
        [
            (
                f"Merged upstream, so the pin now points at the merge commit `{pin[:12]}`. Update Shoal on "
                "this branch until CI passes, then merge. To check locally:"
            ),
            "",
            *fetch_commands(pin),
        ]
    )


def plan(
    pull: PullRequest,
    files: list[ChangedFile],
    tracker: Tracker | None,
    linked: frozenset[str],
    *,
    covered: bool = False,
    report: str | None = None,
    coverage: str | None = None,
) -> Change | Skip | None:
    """What to do so the Shoal pull request for `pull` reflects it; `None` when nothing is needed.

    `covered` says whether `main` already pins a revision that includes the merged change. Acts on
    what changed since the pull request's record, never on its current labels or state alone, so a
    person who reopens or closes one, or removes a label, is not overruled on the next run.
    """
    state = pull.upstream_state
    result = triage(files, linked)
    verdict = result.verdict
    if tracker is not None and tracker.merged:
        return None
    if tracker is None:
        if state is UpstreamState.CLOSED:
            return Skip(pull.number, "closed upstream without merging")
        if verdict is Verdict.UNRELATED:
            return Skip(pull.number, f"unrelated: {', '.join(result.topics)}")
        if covered:
            return Skip(pull.number, f"{DEFAULT_BRANCH} already pins a revision that includes it")
    previous = tracker.mirror if tracker is not None else Mirror(pr=pull.number)
    is_open = tracker.is_open if tracker is not None else True
    # A pull request whose first run failed part way still has the pending record (no verdict or
    # state); it takes every transition from nothing, as a new one would.
    reopen_or_close: str | None = None
    comments: list[str] = []
    if tracker is not None and verdict is not previous.verdict:
        if verdict is Verdict.UNRELATED and is_open:
            reopen_or_close = "closed"
            comments.append(unrelated_comment(result))
        elif previous.verdict is Verdict.UNRELATED and not is_open and state is not UpstreamState.CLOSED:
            reopen_or_close = "open"
            touches = ", ".join(result.areas) or "pages a person should triage"
            comments.append(f"Reopening: the upstream change now touches {touches}.")
    elif (
        verdict is Verdict.RELATED
        and previous.verdict is not None
        and (added := sorted(set(result.areas) - set(previous.areas)))
    ):
        comments.append(f"New upstream commits now also touch {', '.join(added)}.")
    if tracker is not None and state is not previous.state and verdict is not Verdict.UNRELATED:
        if state is UpstreamState.MERGED and covered:
            if is_open:
                reopen_or_close = "closed"
            comments.append(COVERED_COMMENT)
        elif state is UpstreamState.MERGED:
            comments.append(merged_comment(pull.target))
            if not is_open and previous.state is UpstreamState.CLOSED:
                reopen_or_close = "open"
        elif state is UpstreamState.CLOSED and is_open:
            reopen_or_close = "closed"
            comments.append("Closed upstream without merging, so there is nothing to update.")
        elif state is UpstreamState.OPEN and previous.state is UpstreamState.CLOSED and not is_open:
            reopen_or_close = "open"
            comments.append("Reopened upstream.")
    # The branch of a closed pull request stays as it is: GitHub cannot reopen one whose branch was
    # rewritten while it was closed.
    open_after = reopen_or_close == "open" or (is_open and reopen_or_close != "closed")
    moves = (
        open_after
        and verdict is not Verdict.UNRELATED
        and state is not UpstreamState.CLOSED
        and not covered
        and pull.target != previous.pin
    )
    mirror = Mirror(
        pull.number, pull.head.sha, state, verdict, result.areas, pull.target if moves else previous.pin
    )
    title = tracker_title(pull)
    body = render_body(pull, files, result, mirror, report)
    change = Change(
        upstream=pull.number,
        pull=tracker.number if tracker is not None else None,
        title=title,
        body=body,
        pin=pull.target if moves else None,
        coverage=coverage if moves else None,
        state=reopen_or_close,
        comments=comments,
        edit=tracker is None or tracker.title != title or tracker.body != body,
    )
    current = tracker.labels if tracker is not None else frozenset[str]()
    wanted = mirror.labels
    change.add_labels = sorted((wanted - previous.labels - current) | ({LABEL_TRACKER} - current))
    change.remove_labels = sorted((previous.labels - wanted) & current)
    return None if change.is_empty else change


def parse_tracker(pull: ShoalPull) -> Tracker | None:
    """The record a Shoal pull request carries, or `None` when its body has no readable one."""
    body = pull.body or ""
    match = MARKER.search(body)
    if match is None:
        return None
    try:
        mirror = msgspec.json.decode(match.group(1), type=Mirror)
    except msgspec.DecodeError:
        return None
    labels = frozenset(label.name for label in pull.labels)
    merged = pull.merged_at is not None
    return Tracker(pull.number, pull.title, body, pull.state == "open", merged, labels, mirror)


class GitHubApi(Protocol):
    """The GitHub calls the mirror makes."""

    def upstream_pulls(self, since: datetime) -> Iterator[PullRequest]:
        """Upstream pull requests updated at or after `since`, most recent first."""
        ...

    def upstream_pull(self, number: int) -> PullRequest:
        """One upstream pull request."""
        ...

    def pull_files(self, number: int) -> list[ChangedFile]:
        """The files an upstream pull request changes."""
        ...

    def upstream_contains(self, revision: str, commit: str) -> bool:
        """Whether upstream `revision` includes `commit`."""
        ...

    def find_pull(self, branch: str) -> ShoalPull | None:
        """The latest Shoal pull request from `branch`, open or not."""
        ...

    def open_pulls(self) -> list[ShoalPull]:
        """Every open Shoal pull request from a mirror branch."""
        ...

    def main_head(self) -> str:
        """The commit `main` points at."""
        ...

    def read_lock(self, revision: str) -> str | None:
        """The docs revision `discord-api-docs.lock` pins at a Shoal revision, if the file exists."""
        ...

    def branch(self, name: str) -> Branch | None:
        """A mirror branch, or `None` if it does not exist."""
        ...

    def commit_files(self, parent: str, files: dict[str, str], message: str) -> str:
        """Commit `files` (path to content) on top of `parent`, as the mirror; returns the commit."""
        ...

    def set_branch(self, name: str, commit: str, *, create: bool, force: bool) -> None:
        """Point a branch at a commit."""
        ...

    def create_pull(self, title: str, body: str, branch: str) -> int:
        """Open a pull request from `branch` into `main`; returns its number."""
        ...

    def edit_pull(self, number: int, fields: dict[str, str]) -> None:
        """Change a pull request's title, body or state."""
        ...

    def comment(self, number: int, body: str) -> None:
        """Comment on a pull request."""
        ...

    def add_labels(self, number: int, labels: list[str]) -> None:
        """Add labels to a pull request."""
        ...

    def remove_label(self, number: int, label: str) -> None:
        """Remove a label from a pull request; a label already gone is not an error."""
        ...

    def labels(self) -> set[str]:
        """The names of the repository's labels."""
        ...

    def create_label(self, name: str, color: str, description: str) -> None:
        """Add a label to the repository."""
        ...

    def last_success(self, workflow: str) -> datetime | None:
        """When the last successful scheduled run of a workflow started; manual runs do not count."""
        ...


def retry_delay(error: urllib.error.HTTPError) -> float | None:
    """How long to wait before retrying a failed request, or `None` when retrying cannot help.

    GitHub answers a rate limit with 403 or 429 and says when to retry; a 5xx is worth one more try.
    """
    headers = error.headers
    if error.code in {HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS}:
        if (after := headers.get("Retry-After")) is not None:
            return min(float(after), MAX_RETRY_DELAY)
        if headers.get("X-RateLimit-Remaining") == "0" and (reset := headers.get("X-RateLimit-Reset")):
            return min(max(float(reset) - time.time(), 1.0), MAX_RETRY_DELAY)
        return None
    return RETRY_DELAY if error.code >= HTTPStatus.INTERNAL_SERVER_ERROR else None


class GitHub(GitHubApi):
    """GitHub's REST API over urllib, authenticated with a token."""

    __slots__ = ("_api", "_pause", "_repository", "_token")

    def __init__(
        self,
        token: str | None,
        repository: str,
        *,
        api: str = API,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token = token
        self._repository = repository
        self._api = api
        self._pause = pause

    def _request(self, method: str, url: str, body: object = None) -> tuple[bytes, str | None]:
        """Send one request; returns the body and the next page's URL, if any."""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "shoal-upstream-docs-mirror",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        data = None if body is None else msgspec.json.encode(body)
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url if "://" in url else self._api + url, data, headers, method=method
        )
        attempt = 1
        while True:
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    content: bytes = response.read()
                    next_page = re.search(r'<([^>]+)>;\s*rel="next"', response.headers.get("Link", ""))
            except urllib.error.HTTPError as error:
                delay = retry_delay(error)
                if delay is None or attempt == RETRIES:
                    raise
                print(f"retrying {method} {url} in {delay:.0f}s: {error}", file=sys.stderr)
                error.close()
                self._pause(delay)
                attempt += 1
                continue
            if method != "GET":
                self._pause(WRITE_PAUSE)
            return content, next_page.group(1) if next_page else None

    def _get_or_none(self, url: str) -> bytes | None:
        """GET `url`, or `None` when it does not exist."""
        try:
            content, _ = self._request("GET", url)
        except urllib.error.HTTPError as error:
            if error.code != HTTPStatus.NOT_FOUND:
                raise
            error.close()
            return None
        return content

    def _pages[T](self, url: str, page_type: type[list[T]]) -> Iterator[T]:
        next_url: str | None = url
        while next_url is not None:
            content, next_url = self._request("GET", next_url)
            yield from msgspec.json.decode(content, type=page_type)

    @property
    def _repo(self) -> str:
        return f"/repos/{self._repository}"

    @override
    def upstream_pulls(self, since: datetime) -> Iterator[PullRequest]:
        url = f"/repos/{UPSTREAM}/pulls?state=all&sort=updated&direction=desc&per_page=100"
        for pull in self._pages(url, list[PullRequest]):
            if pull.updated < since:
                return
            yield pull

    @override
    def upstream_pull(self, number: int) -> PullRequest:
        content, _ = self._request("GET", f"/repos/{UPSTREAM}/pulls/{number}")
        return msgspec.json.decode(content, type=PullRequest)

    @override
    def pull_files(self, number: int) -> list[ChangedFile]:
        return list(self._pages(f"/repos/{UPSTREAM}/pulls/{number}/files?per_page=100", list[ChangedFile]))

    @override
    def upstream_contains(self, revision: str, commit: str) -> bool:
        content, _ = self._request("GET", f"/repos/{UPSTREAM}/compare/{commit}...{revision}?per_page=1")
        return msgspec.json.decode(content, type=Comparison).status in {"ahead", "identical"}

    @override
    def find_pull(self, branch: str) -> ShoalPull | None:
        owner = self._repository.split("/", 1)[0]
        head = urllib.parse.quote(f"{owner}:{branch}", safe="")
        pulls = list(self._pages(f"{self._repo}/pulls?head={head}&state=all&per_page=100", list[ShoalPull]))
        return max(pulls, key=lambda pull: pull.number, default=None)

    @override
    def open_pulls(self) -> list[ShoalPull]:
        pulls = self._pages(f"{self._repo}/pulls?state=open&per_page=100", list[ShoalPull])
        return [pull for pull in pulls if pull.head.ref.startswith(BRANCH_PREFIX)]

    @override
    def main_head(self) -> str:
        content, _ = self._request("GET", f"{self._repo}/git/ref/heads/{DEFAULT_BRANCH}")
        return msgspec.json.decode(content, type=Ref).object.sha

    @override
    def read_lock(self, revision: str) -> str | None:
        content = self._get_or_none(f"{self._repo}/contents/{LOCK_FILE}?ref={revision}")
        if content is None:
            return None
        encoded = msgspec.json.decode(content, type=FileContent).content
        return base64.b64decode(encoded).decode().strip() or None

    @override
    def branch(self, name: str) -> Branch | None:
        content = self._get_or_none(f"{self._repo}/git/ref/heads/{name}")
        if content is None:
            return None
        sha = msgspec.json.decode(content, type=Ref).object.sha
        compared, _ = self._request("GET", f"{self._repo}/compare/{DEFAULT_BRANCH}...{sha}")
        comparison = msgspec.json.decode(compared, type=Comparison)
        owned = all(entry.commit.author.email == COMMIT_AUTHOR["email"] for entry in comparison.commits)
        return Branch(sha, owned, comparison.behind_by)

    @override
    def commit_files(self, parent: str, files: dict[str, str], message: str) -> str:
        content, _ = self._request("GET", f"{self._repo}/git/commits/{parent}")
        base_tree = msgspec.json.decode(content, type=GitCommit).tree.sha
        entries = [
            {"path": path, "mode": "100644", "type": "blob", "content": text} for path, text in files.items()
        ]
        content, _ = self._request(
            "POST", f"{self._repo}/git/trees", {"base_tree": base_tree, "tree": entries}
        )
        tree = msgspec.json.decode(content, type=GitObject).sha
        commit = {"message": message, "tree": tree, "parents": [parent], "author": COMMIT_AUTHOR}
        content, _ = self._request("POST", f"{self._repo}/git/commits", commit)
        return msgspec.json.decode(content, type=GitObject).sha

    @override
    def set_branch(self, name: str, commit: str, *, create: bool, force: bool) -> None:
        if create:
            self._request("POST", f"{self._repo}/git/refs", {"ref": f"refs/heads/{name}", "sha": commit})
        else:
            self._request("PATCH", f"{self._repo}/git/refs/heads/{name}", {"sha": commit, "force": force})

    @override
    def create_pull(self, title: str, body: str, branch: str) -> int:
        fields = {"title": title, "body": body, "head": branch, "base": DEFAULT_BRANCH}
        content, _ = self._request("POST", f"{self._repo}/pulls", fields)
        return msgspec.json.decode(content, type=ShoalPull).number

    @override
    def edit_pull(self, number: int, fields: dict[str, str]) -> None:
        self._request("PATCH", f"{self._repo}/pulls/{number}", fields)

    @override
    def comment(self, number: int, body: str) -> None:
        self._request("POST", f"{self._repo}/issues/{number}/comments", {"body": body})

    @override
    def add_labels(self, number: int, labels: list[str]) -> None:
        self._request("POST", f"{self._repo}/issues/{number}/labels", {"labels": labels})

    @override
    def remove_label(self, number: int, label: str) -> None:
        name = urllib.parse.quote(label, safe="")
        try:
            self._request("DELETE", f"{self._repo}/issues/{number}/labels/{name}")
        except urllib.error.HTTPError as error:
            # Someone removed it since the pull requests were read: the label is gone either way.
            if error.code != HTTPStatus.NOT_FOUND:
                raise
            error.close()

    @override
    def labels(self) -> set[str]:
        return {label.name for label in self._pages(f"{self._repo}/labels?per_page=100", list[Label])}

    @override
    def create_label(self, name: str, color: str, description: str) -> None:
        body = {"name": name, "color": color, "description": description}
        self._request("POST", f"{self._repo}/labels", body)

    @override
    def last_success(self, workflow: str) -> datetime | None:
        query = "event=schedule&status=success&per_page=1"
        content, _ = self._request("GET", f"{self._repo}/actions/workflows/{workflow}/runs?{query}")
        runs = msgspec.json.decode(content, type=WorkflowRuns).workflow_runs
        return datetime.fromisoformat(runs[0].created_at) if runs else None


def check_checkout(repository: Path) -> DocsCheck:
    """Run `scripts/check_docs.py`'s checks against a docs checkout."""
    problems, coverage = check(repository)
    return DocsCheck(tuple(problems), coverage)


class DocsCheckout:
    """A docs checkout that can be moved to any upstream revision, with each revision's check cached."""

    __slots__ = ("_checker", "_path", "_remote", "_results")

    def __init__(
        self,
        path: Path,
        *,
        remote: str = f"https://github.com/{UPSTREAM}",
        checker: Callable[[Path], DocsCheck] = check_checkout,
    ) -> None:
        self._path = path
        self._remote = remote
        self._checker = checker
        self._results: dict[str, DocsCheck] = {}

    def _git(self, *arguments: str) -> None:
        command = ["git", "-C", str(self._path), *arguments]
        subprocess.run(command, check=True, capture_output=True)  # noqa: S603  # fixed git arguments, no shell

    def check(self, revision: str) -> DocsCheck:
        """Check Shoal against `revision`, fetching it first (blobs on demand)."""
        if revision not in self._results:
            if not (self._path / ".git").exists():
                self._path.mkdir(parents=True, exist_ok=True)
                self._git("init", "--quiet")
            self._git("fetch", "--quiet", "--depth", "1", "--filter=blob:none", self._remote, revision)
            self._git("checkout", "--quiet", "--detach", "--force", revision)
            self._results[revision] = self._checker(self._path)
        return self._results[revision]


def push_pin(api: GitHubApi, change: Change, main: str) -> None:
    """Move the branch's pin to `change.pin`.

    A branch holding only the mirror's commits is rebuilt on `main` with the pin and the coverage report
    for it. Once someone else has committed to it, the mirror adds a commit that moves only the pin,
    and leaves the report to them.
    """
    if change.pin is None:
        return
    message = f"Check Shoal against {UPSTREAM}#{change.upstream} at {change.pin[:12]}"
    current = api.branch(change.branch)
    if current is None or current.owned:
        files = {LOCK_FILE: f"{change.pin}\n"}
        if change.coverage is not None:
            files[COVERAGE_FILE] = change.coverage
        commit = api.commit_files(main, files, message)
        api.set_branch(change.branch, commit, create=current is None, force=True)
    elif api.read_lock(current.sha) != change.pin:
        commit = api.commit_files(current.sha, {LOCK_FILE: f"{change.pin}\n"}, message)
        api.set_branch(change.branch, commit, create=False, force=False)


FAILURES = (urllib.error.URLError, TimeoutError, subprocess.CalledProcessError, msgspec.DecodeError)
"""What one pull request can fail with without stopping the others: GitHub, the network, git, or a reply
that does not decode."""


def apply(change: Change, api: GitHubApi, main: str) -> None:
    """Carry out a change.

    A pull request is reopened before its branch moves (GitHub refuses to reopen one whose branch was
    rewritten while it was closed) and closed after its comments. The record in the body is written
    last, so a run that fails part way is redone by the next one: a comment may then appear twice, but
    none is lost.
    """
    if change.pull is not None and change.state == "open":
        api.edit_pull(change.pull, {"state": "open"})
    push_pin(api, change, main)
    number = change.pull
    if number is None:
        pending = change.body.rpartition("<!-- upstream-docs-mirror ")[0] + marker(Mirror(pr=change.upstream))
        number = api.create_pull(change.title, pending, change.branch)
    for comment in change.comments:
        api.comment(number, comment)
    if change.state == "closed":
        api.edit_pull(number, {"state": "closed"})
    if change.add_labels:
        api.add_labels(number, change.add_labels)
    for label in change.remove_labels:
        api.remove_label(number, label)
    if change.edit:
        api.edit_pull(number, {"title": change.title, "body": change.body})


def refresh(
    api: GitHubApi, main: str, main_pin: str | None, docs: DocsCheckout | None, *, dry_run: bool
) -> tuple[int, list[int]]:
    """Rebuild on `main` every open mirror branch that holds only the mirror's commits and is behind it.

    Every mirror branch changes the same pin, so once one is merged the others would conflict; rebuilt,
    they stay mergeable. A branch whose pin `main` already includes is left alone, so merging it cannot
    move the pin back. Returns how many were (or would be) rebuilt, and the upstream pull requests
    whose branch failed.
    """
    rebuilt = 0
    failed: list[int] = []
    for pull in api.open_pulls():
        tracker = parse_tracker(pull)
        if tracker is None or tracker.mirror.pin is None:
            continue
        pin = tracker.mirror.pin
        try:
            branch = api.branch(pull.head.ref)
            if branch is None or not branch.owned or branch.behind == 0:
                continue
            if main_pin is not None and api.upstream_contains(main_pin, pin):
                print(
                    f"leave {pull.head.ref} (#{pull.number}): {DEFAULT_BRANCH} already pins past {pin[:12]}"
                )
                continue
            print(f"rebuild {pull.head.ref} (#{pull.number}) on {DEFAULT_BRANCH}")
            if not dry_run:
                coverage = docs.check(pin).coverage if docs is not None else None
                push_pin(
                    api, Change(tracker.mirror.pr, pull.number, "", "", pin=pin, coverage=coverage), main
                )
        except FAILURES as error:
            print(f"error: rebuilding {pull.head.ref} (#{pull.number}): {error}", file=sys.stderr)
            failed.append(tracker.mirror.pr)
            continue
        rebuilt += 1
    return rebuilt, failed


def ensure_labels(api: GitHubApi) -> None:
    """Create the labels this script sets that the repository does not have yet (names ignore case)."""
    existing = {name.casefold() for name in api.labels()}
    for name, (color, description) in LABELS.items():
        if name.casefold() not in existing:
            api.create_label(name, color, description)


def sync(
    api: GitHubApi,
    pulls: Iterable[PullRequest],
    linked: frozenset[str],
    docs: DocsCheckout | None,
    *,
    dry_run: bool,
    pin: str | None = None,
) -> tuple[list[Change], list[int]]:
    """Bring the Shoal pull request of every upstream pull request in `pulls` up to date.

    Returns what was (or would be) done, and the upstream pull requests that failed. A failure is
    reported and the rest carry on; the run then fails, so the next one looks back as far and tries
    them again. `pin` stands in for the revision `main` pins, before it pins one.
    """
    # Listed before any write: pages read while writing shift as pull requests are updated, and
    # would hand back one already done.
    unique: dict[int, PullRequest] = {}
    for pull in pulls:
        unique.setdefault(pull.number, pull)
    if not dry_run:
        ensure_labels(api)
    main = api.main_head()
    main_pin = pin or api.read_lock(main)
    _, failed = refresh(api, main, main_pin, docs, dry_run=dry_run)
    changes: list[Change] = []
    for pull in unique.values():
        try:
            files = api.pull_files(pull.number)
            existing = api.find_pull(branch_name(pull.number))
            tracker = parse_tracker(existing) if existing is not None else None
            if existing is not None and tracker is None:
                print(
                    f"warning: #{existing.number} is on {existing.head.ref} but has no readable record",
                    file=sys.stderr,
                )
                continue
            covered = (
                pull.upstream_state is UpstreamState.MERGED
                and main_pin is not None
                and api.upstream_contains(main_pin, pull.target)
            )
            report = coverage = None
            wanted = (
                pull.upstream_state is not UpstreamState.CLOSED
                and not covered
                and triage(files, linked).verdict is not Verdict.UNRELATED
            )
            if docs is not None and main_pin is not None and wanted:
                base, target = docs.check(main_pin), docs.check(pull.target)
                report = render_report(base, target, main_pin, pull.target, touched_pages(files))
                coverage = target.coverage
            outcome = plan(pull, files, tracker, linked, covered=covered, report=report, coverage=coverage)
            if outcome is None:
                continue
            print(outcome.describe())
            if isinstance(outcome, Skip):
                continue
            if not dry_run:
                apply(outcome, api, main)
        except FAILURES as error:
            print(f"error: {UPSTREAM}#{pull.number}: {error}", file=sys.stderr)
            failed.append(pull.number)
            continue
        changes.append(outcome)
    return changes, failed


def unmatched(repository: Path) -> list[str]:
    """Files in a docs checkout that no rule covers."""
    paths = (
        path.relative_to(repository).as_posix()
        for path in repository.rglob("*")
        if path.is_file() and not {".git", "node_modules"} & set(path.relative_to(repository).parts)
    )
    return sorted(path for path in paths if rule_for(path) is None)


def main() -> int:
    """Mirror and triage; see the module docstring."""
    parser = argparse.ArgumentParser(description="Open Shoal pull requests for Discord docs pull requests.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY))
    parser.add_argument("--since-hours", type=float, default=24.0, help="look back this far (default 24)")
    parser.add_argument("--workflow", help="look back to this workflow's last successful run instead")
    parser.add_argument(
        "--pull", type=int, action="append", default=[], help="mirror this upstream pull request"
    )
    parser.add_argument(
        "--docs-repo", type=Path, help="a docs checkout to check each revision in (moved freely)"
    )
    parser.add_argument("--pin", help="compare against this docs revision instead of the one main pins")
    parser.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    parser.add_argument("--unmatched", type=Path, metavar="DOCS_REPO", help="list paths no rule covers")
    options = parser.parse_args()

    if options.unmatched is not None:
        paths = unmatched(options.unmatched)
        for path in paths:
            print(path)
        print(f"{len(paths)} paths no triage rule covers")
        return 1 if paths else 0
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("set GITHUB_TOKEN (locally: GITHUB_TOKEN=$(gh auth token))", file=sys.stderr)
        return 2
    api = GitHub(token, options.repository)
    pulls: Iterable[PullRequest]
    if options.pull:
        pulls = [api.upstream_pull(number) for number in options.pull]
    else:
        since = datetime.now(UTC) - timedelta(hours=options.since_hours)
        if options.workflow is not None and (last := api.last_success(options.workflow)) is not None:
            since = max(last - RUN_OVERLAP, datetime.now(UTC) - MAX_LOOKBACK)
            if since > last - RUN_OVERLAP:
                print(f"warning: no successful run since {last.isoformat()}; looking back {MAX_LOOKBACK}")
        print(f"pull requests updated since {since.isoformat(timespec='seconds')}")
        pulls = api.upstream_pulls(since)
    docs = DocsCheckout(options.docs_repo) if options.docs_repo is not None else None
    linked = linked_pages()
    changes, failed = sync(api, pulls, linked, docs, dry_run=options.dry_run, pin=options.pin)
    done = "would change" if options.dry_run else "changed"
    print(f"{len(changes)} pull requests {done}, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
