import hashlib
import subprocess
import sys
import threading
import time
import urllib.error
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import override

import msgspec
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import mirror_upstream_prs as mirror
from mirror_upstream_prs import (
    Branch,
    Change,
    ChangedFile,
    DocsCheck,
    Mirror,
    PullRequest,
    ShoalPull,
    Skip,
    Tracker,
    UpstreamState,
    Verdict,
)

NOTHING_LINKED: frozenset[str] = frozenset()
URL = "https://github.com/discord/discord-api-docs/pull/8679"
RESOURCE = "developers/resources/message.mdx"
SOCIAL = "developers/discord-social-sdk/development-guides/lobbies.mdx"
MESSAGE_PAGE = "https://docs.discord.com/developers/resources/message"


def pull(
    number: int = 8679,
    *,
    title: str = "Document an attachment flag",
    state: str = "open",
    merged: bool = False,
    head: str = "abc",
    merge: str | None = "test-merge",
) -> PullRequest:
    return PullRequest(
        number=number,
        title=title,
        html_url=f"https://github.com/discord/discord-api-docs/pull/{number}",
        state=state,
        updated_at="2026-10-20T12:00:00Z",
        user=mirror.GitHubUser(login="someone"),
        head=mirror.Head(sha=head),
        merged_at="2026-10-21T12:00:00Z" if merged else None,
        merge_commit_sha=merge,
    )


def files(*paths: str) -> list[ChangedFile]:
    return [ChangedFile(filename=path, status="modified", additions=3, deletions=1) for path in paths]


def record(head: str = "abc") -> Mirror:
    return Mirror(pr=8679, head=head)


def planned(
    upstream: PullRequest,
    changed: list[ChangedFile],
    existing: Tracker | None,
    *,
    covered: bool = False,
    linked: frozenset[str] = NOTHING_LINKED,
) -> Change:
    change = mirror.plan(upstream, changed, existing, linked, covered=covered)
    assert isinstance(change, Change)
    return change


def current(
    upstream: PullRequest,
    changed: list[ChangedFile],
    *,
    is_open: bool | None = None,
    merged: bool = False,
    labels: frozenset[str] | None = None,
) -> Tracker:
    """A pull request that already reflects `upstream`, as the last run left it."""
    result = mirror.triage(changed, NOTHING_LINKED)
    state = upstream.upstream_state
    previous = Mirror(
        upstream.number, upstream.head.sha, state, result.verdict, result.areas, upstream.target
    )
    left_open = result.verdict is not Verdict.UNRELATED and state is not UpstreamState.CLOSED
    return Tracker(
        number=12,
        title=mirror.tracker_title(upstream),
        body=mirror.render_body(upstream, changed, result, previous, None),
        is_open=left_open if is_open is None else is_open,
        merged=merged,
        labels=previous.labels | {mirror.LABEL_TRACKER} if labels is None else labels,
        mirror=previous,
    )


@pytest.mark.parametrize(
    ("path", "areas"),
    [
        ("developers/events/gateway-events.mdx", ("gateway", "payloads")),
        ("developers/events/overview.mdx", ("gateway",)),
        ("developers/topics/rpc.mdx", ()),
        ("developers/something-new/page.mdx", None),
    ],
)
def test_the_longest_prefix_decides_a_path(path: str, areas: tuple[str, ...] | None) -> None:
    rule = mirror.rule_for(path)
    assert (rule.areas if rule is not None else None) == areas


def test_rules_are_alphabetical_unique_and_name_known_labels() -> None:
    prefixes = [rule.prefix for rule in mirror.RULES]
    assert prefixes == sorted(prefixes)
    assert len(set(prefixes)) == len(prefixes)
    areas = {area for rule in mirror.RULES for area in rule.areas}
    assert areas <= set(mirror.LABELS)
    assert list(mirror.LABELS) == sorted(mirror.LABELS)


def test_any_related_path_makes_the_change_related() -> None:
    result = mirror.triage(files(SOCIAL, RESOURCE, "developers/change-log.mdx"), NOTHING_LINKED)
    assert result.verdict is Verdict.RELATED
    assert result.areas == ("changelog", "payloads", "rest")


def test_a_change_only_about_unrelated_pages_is_unrelated() -> None:
    result = mirror.triage(files(SOCIAL, "images/lobby.png"), NOTHING_LINKED)
    assert result.verdict is Verdict.UNRELATED
    assert result.topics == ("Social SDK", "site assets")


@pytest.mark.parametrize(
    ("paths", "linked"),
    [
        ((SOCIAL, "developers/brand-new/page.mdx"), NOTHING_LINKED),
        (("developers/monetization/overview.mdx",), frozenset({"developers/monetization/overview.mdx"})),
        (("developers/change-log.mdx",), NOTHING_LINKED),
        ((), NOTHING_LINKED),
    ],
    ids=["unknown path", "linked page", "change log only", "no files"],
)
def test_a_person_decides_what_the_rules_cannot(paths: tuple[str, ...], linked: frozenset[str]) -> None:
    assert mirror.triage(files(*paths), linked).verdict is Verdict.NEEDS_TRIAGE


def test_a_rename_counts_both_paths() -> None:
    moved = ChangedFile(
        filename=SOCIAL, status="renamed", additions=0, deletions=0, previous_filename=RESOURCE
    )
    assert mirror.triage([moved], NOTHING_LINKED).verdict is Verdict.RELATED
    assert mirror.touched_pages([moved]) == {
        MESSAGE_PAGE,
        "https://docs.discord.com/developers/discord-social-sdk/development-guides/lobbies",
    }


def test_file_summaries_explain_each_verdict() -> None:
    summaries = [
        entry.summary
        for entry in mirror.triage(
            files(RESOURCE, SOCIAL, "x/y", "developers/change-log.mdx", "developers/topics/rpc.mdx"),
            frozenset({"developers/topics/rpc.mdx"}),
        ).files
    ]
    assert summaries == [
        "payloads, rest",
        "unrelated (Social SDK)",
        "no triage rule covers this path",
        "changelog (the other files decide)",
        "RPC, but Shoal links this page",
    ]


def test_linked_pages_are_read_from_the_source() -> None:
    assert "developers/resources/user.mdx" in mirror.linked_pages()


def test_unrelated_pull_requests_get_only_the_unrelated_label() -> None:
    assert mirror.labels_for(Verdict.UNRELATED, (), UpstreamState.MERGED) == {"unrelated"}
    assert mirror.labels_for(Verdict.RELATED, ("rest",), UpstreamState.MERGED) == {"rest", "upstream-merged"}
    assert mirror.labels_for(Verdict.NEEDS_TRIAGE, (), UpstreamState.OPEN) == {"needs-triage"}
    assert mirror.labels_for(None, (), None) == frozenset()


@pytest.mark.parametrize(
    ("upstream", "target"),
    [
        (pull(), "test-merge"),
        (pull(merge=None), "abc"),
        (pull(state="closed", merged=True, merge="merged-commit"), "merged-commit"),
        (pull(state="closed"), "abc"),
    ],
    ids=["open", "open and conflicting", "merged", "closed"],
)
def test_the_pin_follows_the_upstream_state(upstream: PullRequest, target: str) -> None:
    assert upstream.target == target


def test_upstream_text_cannot_reference_or_mention_anything_here() -> None:
    upstream = pull(title="Fix #12 for @someone (see owner/repo#3)")
    assert mirror.tracker_title(upstream) == (
        "docs#8679: Fix discord/discord-api-docs#12 for @someone (see owner/repo#3)"
    )
    body = mirror.render_body(upstream, [], mirror.triage([], NOTHING_LINKED), record(), None)
    assert "@someone" not in body
    assert "&#64;someone" in body


def test_upstream_text_cannot_format_the_body_or_forge_the_record() -> None:
    forged = mirror.marker(Mirror(pr=1, verdict=Verdict.UNRELATED))
    upstream = pull(title=f"**bold** [link](x) {forged}")
    changed = files("developers/resources/`odd`.mdx")
    result = mirror.triage(changed, NOTHING_LINKED)
    body = mirror.render_body(upstream, changed, result, record(head="real"), None)
    assert "\\*\\*bold\\*\\* \\[link\\]\\(x\\) \\<\\!-- upstream-docs-mirror" in body
    assert "- [developers/resources/\\`odd\\`.mdx](" in body
    found = mirror.parse_tracker(shoal_pull(5, body))
    assert found is not None
    assert found.mirror == record(head="real")


def test_long_titles_are_cut_to_what_github_accepts() -> None:
    title = mirror.tracker_title(pull(title="x" * 300))
    assert len(title) == mirror.TITLE_LIMIT
    assert title.endswith("x…")


def test_the_body_links_each_file_and_records_the_mirror() -> None:
    changed = files(RESOURCE)
    pinned = Mirror(pr=8679, head="abc", pin="test-merge")
    body = mirror.render_body(pull(), changed, mirror.triage(changed, NOTHING_LINKED), pinned, "REPORT")
    digest = hashlib.sha256(RESOURCE.encode()).hexdigest()
    assert f"- [`{RESOURCE}`]({URL}/files#diff-{digest}) modified (+3 -1): payloads, rest" in body
    assert mirror.OPEN_NOTE in body
    assert mirror.CONFLICT_NOTE not in body
    assert "REPORT" in body
    assert "Pins `discord-api-docs.lock` to [`test-merge`]" in body
    found = mirror.parse_tracker(shoal_pull(5, body, labels=["rest"]))
    assert found is not None
    assert found.mirror == pinned
    assert found.labels == {"rest"}


def test_the_body_says_what_to_do_in_each_upstream_state() -> None:
    result = mirror.triage(files(RESOURCE), NOTHING_LINKED)
    conflicting = mirror.render_body(pull(merge=None), [], result, record(), None)
    assert mirror.CONFLICT_NOTE in conflicting
    assert "Not run: the mirror had no docs checkout." in conflicting
    merged = mirror.render_body(pull(state="closed", merged=True, merge="m" * 40), [], result, record(), None)
    assert "**Merged upstream.**" in merged
    assert f"fetch --depth 1 https://github.com/discord/discord-api-docs {'m' * 40}" in merged
    closed = mirror.render_body(pull(state="closed"), [], result, record(), None)
    assert "**Closed upstream without merging**" in closed


def test_long_file_lists_are_cut_short() -> None:
    changed = files(*(f"images/{index:04}.png" for index in range(1000)))
    body = mirror.render_body(pull(), changed, mirror.triage(changed, NOTHING_LINKED), record(), None)
    listed = body.count("](https://github.com/discord/discord-api-docs/pull/8679/files#diff-")
    assert f"- and {1000 - listed} more on the upstream pull request" in body
    assert len(body) < 65536


def shoal_pull(
    number: int,
    body: str | None,
    *,
    labels: list[str] | None = None,
    state: str = "open",
    merged: bool = False,
) -> ShoalPull:
    return ShoalPull(
        number=number,
        title="t",
        state=state,
        head=mirror.Head(sha="branch-head", ref=mirror.branch_name(8679)),
        labels=[mirror.Label(name=name) for name in labels or []],
        body=body,
        merged_at="2026-10-22T00:00:00Z" if merged else None,
    )


@pytest.mark.parametrize("body", [None, "no record", '<!-- upstream-docs-mirror {"pr": "x"} -->'])
def test_pull_requests_without_a_readable_record_are_not_tracked(body: str | None) -> None:
    assert mirror.parse_tracker(shoal_pull(1, body)) is None


def check(problems: tuple[str, ...], coverage: str) -> DocsCheck:
    return DocsCheck(problems, coverage)


def test_the_report_shows_only_what_changed_on_the_touched_pages() -> None:
    base = check(
        (f"a.py: {MESSAGE_PAGE}#gone -> no anchor", f"b.py: {MESSAGE_PAGE}s#x -> elsewhere"),
        f"| yes | [Old]({MESSAGE_PAGE}#old) |\n| yes | [Other](https://x/other#a) |\n",
    )
    target = check(
        (f"c.py: {MESSAGE_PAGE}#new -> no anchor", f"d.py: {MESSAGE_PAGE}s#y -> elsewhere"),
        f"| yes | [Old]({MESSAGE_PAGE}#old) |\n| no | [New]({MESSAGE_PAGE}#new) |\n",
    )
    report = mirror.render_report(base, target, "a" * 40, "b" * 40, frozenset({MESSAGE_PAGE}))
    assert report.splitlines() == [
        "### Docs check: `aaaaaaaaaaaa` to `bbbbbbbbbbbb`",
        "",
        "Problems Shoal now has (1):",
        "",
        f"- c.py: {MESSAGE_PAGE}#new -> no anchor",
        "",
        "Problems now gone (1):",
        "",
        f"- a.py: {MESSAGE_PAGE}#gone -> no anchor",
        "",
        "Coverage changes on the pages this touches:",
        "",
        "```diff",
        f"+| no | [New]({MESSAGE_PAGE}#new) |",
        "```",
    ]


def test_the_report_says_when_nothing_changed() -> None:
    same = check((), "| yes | row |\n")
    report = mirror.render_report(same, same, "a" * 40, "b" * 40, frozenset({MESSAGE_PAGE}))
    assert report.endswith("No change to the links, routes, events or endpoints Shoal checks.")


def test_long_report_sections_are_capped() -> None:
    problems = tuple(f"p{index}: {MESSAGE_PAGE}#a" for index in range(mirror.REPORT_LINE_LIMIT + 3))
    report = mirror.render_report(check((), ""), check(problems, ""), "a", "b", frozenset({MESSAGE_PAGE}))
    assert "... and 3 more" in report


def test_a_new_related_pull_request_gets_a_pull_request() -> None:
    change = planned(pull(), files(RESOURCE), None)
    assert change.pull is None
    assert change.pin == "test-merge"
    assert change.state is None
    assert change.comments == []
    assert change.add_labels == ["payloads", "rest", "upstream-docs"]
    assert change.describe().splitlines()[:3] == [
        "discord/discord-api-docs#8679 -> new pull request: docs#8679: Document an attachment flag",
        "  pin discord-api-docs.lock to test-merge on upstream/discord-api-docs-8679",
        "  open",
    ]


@pytest.mark.parametrize(
    ("upstream", "changed", "covered", "reason"),
    [
        (pull(state="closed"), files(RESOURCE), False, "closed upstream without merging"),
        (pull(merged=True, state="closed"), files(SOCIAL), False, "unrelated: Social SDK"),
        (
            pull(merged=True, state="closed"),
            files(RESOURCE),
            True,
            "main already pins a revision that includes it",
        ),
    ],
    ids=["closed", "unrelated", "covered"],
)
def test_some_pull_requests_get_none(
    upstream: PullRequest, changed: list[ChangedFile], covered: bool, reason: str
) -> None:
    outcome = mirror.plan(upstream, changed, None, NOTHING_LINKED, covered=covered)
    assert isinstance(outcome, Skip)
    assert outcome == Skip(8679, reason)
    assert outcome.describe() == f"discord/discord-api-docs#8679: no pull request ({reason})"


def test_a_pull_request_merged_before_it_was_mirrored_pins_the_merge() -> None:
    change = planned(pull(state="closed", merged=True, merge="merged-commit"), files(RESOURCE), None)
    assert change.pin == "merged-commit"
    assert change.comments == []
    assert "upstream-merged" in change.add_labels
    assert "**Merged upstream.**" in change.body


def test_an_unchanged_pull_request_needs_nothing() -> None:
    upstream, changed = pull(), files(RESOURCE)
    assert mirror.plan(upstream, changed, current(upstream, changed), NOTHING_LINKED) is None


def test_a_merged_shoal_pull_request_is_left_alone() -> None:
    upstream, changed = pull(), files(RESOURCE)
    existing = current(upstream, changed, merged=True)
    assert mirror.plan(pull(head="new", merge="newer"), changed, existing, NOTHING_LINKED) is None


def test_new_commits_move_the_pin() -> None:
    changed = files(RESOURCE)
    change = planned(pull(head="def", merge="newer"), changed, current(pull(), changed))
    assert change.pin == "newer"
    assert change.comments == []


def test_a_merge_moves_the_pin_and_comments_once() -> None:
    changed = files(RESOURCE)
    existing = current(pull(), changed)
    change = planned(pull(state="closed", merged=True, merge="merged-commit"), changed, existing)
    assert change.pin == "merged-commit"
    assert change.state is None
    assert change.comments == [mirror.merged_comment("merged-commit")]
    assert change.add_labels == ["upstream-merged"]
    assert "update title and body" in change.describe()


def test_a_merge_main_already_pins_past_closes_the_pull_request() -> None:
    changed = files(RESOURCE)
    existing = current(pull(), changed)
    change = planned(
        pull(state="closed", merged=True, merge="merged-commit"), changed, existing, covered=True
    )
    assert change.pin is None
    assert change.state == "closed"
    assert change.comments == [mirror.COVERED_COMMENT]


def test_a_pending_record_takes_every_transition_from_nothing() -> None:
    pending = Tracker(12, "t", "b", is_open=True, merged=False, labels=frozenset(), mirror=Mirror(pr=8679))
    unrelated = planned(pull(), files(SOCIAL), pending)
    assert unrelated.state == "closed"
    assert unrelated.pin is None
    closed = planned(pull(state="closed"), files(RESOURCE), pending)
    assert closed.state == "closed"
    assert closed.comments == ["Closed upstream without merging, so there is nothing to update."]
    resumed = planned(pull(), files(RESOURCE), pending)
    assert resumed.state is None
    assert resumed.pin == "test-merge"


def test_the_branch_of_a_closed_pull_request_stays_as_it_is() -> None:
    changed = files(RESOURCE)
    change = planned(pull(head="def", merge="newer"), changed, current(pull(), changed, is_open=False))
    assert change.pin is None
    assert '"pin":"test-merge"' in change.body


def test_a_close_without_merging_closes_the_pull_request() -> None:
    changed = files(RESOURCE)
    change = planned(pull(state="closed"), changed, current(pull(), changed))
    assert change.state == "closed"
    assert change.pin is None
    assert change.comments == ["Closed upstream without merging, so there is nothing to update."]
    assert "  close" in change.describe()


def test_reopening_upstream_reopens_the_pull_request() -> None:
    changed = files(RESOURCE)
    change = planned(pull(), changed, current(pull(state="closed"), changed, is_open=False))
    assert change.state == "open"
    assert change.comments == ["Reopened upstream."]


def test_merging_after_a_close_reopens_the_pull_request() -> None:
    changed = files(RESOURCE)
    merged = pull(state="closed", merged=True, merge="merged-commit")
    change = planned(merged, changed, current(pull(state="closed"), changed, is_open=False))
    assert change.state == "open"


def test_a_pull_request_closed_by_a_person_stays_closed_on_merge() -> None:
    changed = files(RESOURCE)
    merged = pull(state="closed", merged=True, merge="merged-commit")
    change = planned(merged, changed, current(pull(), changed, is_open=False))
    assert change.state is None
    assert change.comments == [mirror.merged_comment("merged-commit")]


def test_new_commits_that_leave_the_api_close_the_pull_request() -> None:
    existing = current(pull(), files(RESOURCE))
    change = planned(pull(head="def", merge="newer"), files(SOCIAL), existing)
    assert change.state == "closed"
    assert change.pin is None
    assert change.add_labels == ["unrelated"]
    assert change.remove_labels == ["payloads", "rest"]
    assert change.comments[0].startswith("Closing as unrelated: every changed file is now about Social SDK")


def test_new_commits_that_reach_the_api_reopen_the_pull_request() -> None:
    existing = current(pull(), files(SOCIAL))
    change = planned(pull(head="def", merge="newer"), files(SOCIAL, RESOURCE), existing)
    assert change.state == "open"
    assert change.pin == "newer"
    assert change.comments == ["Reopening: the upstream change now touches payloads, rest."]
    assert change.add_labels == ["payloads", "rest"]
    assert change.remove_labels == ["unrelated"]
    assert "  reopen" in change.describe()


def test_new_commits_that_reach_unknown_pages_reopen_the_pull_request() -> None:
    existing = current(pull(), files(SOCIAL))
    change = planned(pull(head="def"), files(SOCIAL, "x/y"), existing)
    assert change.comments == ["Reopening: the upstream change now touches pages a person should triage."]


def test_new_commits_that_touch_another_area_say_so() -> None:
    existing = current(pull(), files(RESOURCE))
    change = planned(pull(head="def"), files(RESOURCE, "developers/events/gateway.mdx"), existing)
    assert change.comments == ["New upstream commits now also touch gateway."]
    assert change.add_labels == ["gateway"]


def test_a_person_who_reopens_an_unrelated_pull_request_is_not_overruled() -> None:
    upstream, changed = pull(), files(SOCIAL)
    reopened = current(upstream, changed, is_open=True, labels=frozenset({mirror.LABEL_TRACKER}))
    assert mirror.plan(upstream, changed, reopened, NOTHING_LINKED) is None


def test_a_person_who_removes_a_label_is_not_overruled() -> None:
    upstream, changed = pull(), files(RESOURCE)
    edited = current(upstream, changed, labels=frozenset({mirror.LABEL_TRACKER, "rest"}))
    assert mirror.plan(upstream, changed, edited, NOTHING_LINKED) is None


def test_a_change_without_edits_describes_only_its_actions() -> None:
    change = Change(upstream=1, pull=3, title="t", body="b", comments=["hi"], edit=False)
    assert change.describe() == "discord/discord-api-docs#1 -> #3: t\n  comment: hi"
    assert not change.is_empty


@dataclass
class FakeApi(mirror.GitHubApi):
    changed: dict[int, list[ChangedFile]] = field(default_factory=dict[int, list[ChangedFile]])
    pulls: dict[str, ShoalPull] = field(default_factory=dict[str, ShoalPull])
    branches: dict[str, Branch] = field(default_factory=dict[str, Branch])
    locks: dict[str, str] = field(default_factory=lambda: {"main-sha": "main-pin"})
    contained: bool = False
    calls: list[tuple[object, ...]] = field(default_factory=list[tuple[object, ...]])

    @override
    def upstream_pulls(self, since: datetime) -> Iterator[PullRequest]:
        raise NotImplementedError

    @override
    def upstream_pull(self, number: int) -> PullRequest:
        raise NotImplementedError

    @override
    def pull_files(self, number: int) -> list[ChangedFile]:
        if number not in self.changed:
            msg = "unreachable"
            raise urllib.error.URLError(msg)
        return self.changed[number]

    @override
    def upstream_contains(self, revision: str, commit: str) -> bool:
        return self.contained

    @override
    def find_pull(self, branch: str) -> ShoalPull | None:
        return self.pulls.get(branch)

    @override
    def open_pulls(self) -> list[ShoalPull]:
        return [found for found in self.pulls.values() if found.state == "open"]

    @override
    def main_head(self) -> str:
        return "main-sha"

    @override
    def read_lock(self, revision: str) -> str | None:
        return self.locks.get(revision)

    @override
    def branch(self, name: str) -> Branch | None:
        return self.branches.get(name)

    @override
    def commit_files(self, parent: str, files: dict[str, str], message: str) -> str:
        self.calls.append(("commit_files", parent, sorted(files), files[mirror.LOCK_FILE]))
        return "new-commit"

    @override
    def set_branch(self, name: str, commit: str, *, create: bool, force: bool) -> None:
        self.calls.append(("set_branch", name, commit, create, force))

    @override
    def create_pull(self, title: str, body: str, branch: str) -> int:
        found = mirror.MARKER.search(body)
        assert found is not None
        self.calls.append(("create_pull", title, found.group(1), branch))
        return 40

    @override
    def edit_pull(self, number: int, fields: dict[str, str]) -> None:
        self.calls.append(("edit_pull", number, sorted(fields)))

    @override
    def comment(self, number: int, body: str) -> None:
        self.calls.append(("comment", number))

    @override
    def add_labels(self, number: int, labels: list[str]) -> None:
        self.calls.append(("add_labels", number, labels))

    @override
    def remove_label(self, number: int, label: str) -> None:
        self.calls.append(("remove_label", number, label))

    @override
    def labels(self) -> set[str]:
        return {"bug", "REST"}

    @override
    def create_label(self, name: str, color: str, description: str) -> None:
        self.calls.append(("create_label", name))

    @override
    def last_success(self, workflow: str) -> datetime | None:
        raise NotImplementedError


class FakeCheckout(mirror.DocsCheckout):
    __slots__ = ("checks", "failing")

    def __init__(self, checks: dict[str, DocsCheck]) -> None:
        super().__init__(Path("unused"))
        self.checks = checks
        self.failing = False

    @override
    def check(self, revision: str) -> DocsCheck:
        if self.failing:
            raise subprocess.CalledProcessError(128, ["git", "fetch"])
        return self.checks[revision]


def writes(api: FakeApi) -> list[tuple[object, ...]]:
    return [call for call in api.calls if call[0] != "create_label"]


def test_a_new_pull_request_is_opened_from_a_pinned_branch_and_recorded_last() -> None:
    api = FakeApi(changed={1: files(RESOURCE)})
    [change], failed = mirror.sync(api, [pull(1)], NOTHING_LINKED, None, dry_run=False)
    assert failed == []
    assert change.pin == "test-merge"
    assert writes(api) == [
        ("commit_files", "main-sha", ["discord-api-docs.lock"], "test-merge\n"),
        ("set_branch", "upstream/discord-api-docs-1", "new-commit", True, True),
        ("create_pull", "docs#1: Document an attachment flag", '{"pr":1}', "upstream/discord-api-docs-1"),
        ("add_labels", 40, ["payloads", "rest", "upstream-docs"]),
        ("edit_pull", 40, ["body", "title"]),
    ]
    made = {call[1] for call in api.calls if call[0] == "create_label"}
    assert made == set(mirror.LABELS) - {"rest"}


def test_unrelated_and_covered_pull_requests_open_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    merged = pull(2, state="closed", merged=True, merge="merged-commit")
    api = FakeApi(changed={1: files(SOCIAL), 2: files(RESOURCE)}, contained=True)
    changes, _ = mirror.sync(api, [pull(1), merged], NOTHING_LINKED, None, dry_run=False)
    assert changes == []
    assert writes(api) == []
    out = capsys.readouterr().out
    assert "#1: no pull request (unrelated: Social SDK)" in out
    assert "#2: no pull request (main already pins a revision that includes it)" in out


def test_an_existing_pull_request_is_updated_in_place() -> None:
    changed = files(SOCIAL)
    existing = current(pull(), changed, is_open=False)
    body = existing.body.replace('"state":"open"', '"state":"closed"')
    api = FakeApi(
        changed={8679: changed},
        pulls={mirror.branch_name(8679): shoal_pull(12, body, state="closed")},
    )
    [change], _ = mirror.sync(api, [pull()], NOTHING_LINKED, None, dry_run=False)
    assert change.pull == 12
    assert ("edit_pull", 12, ["state"]) not in api.calls
    assert api.calls[-1] == ("edit_pull", 12, ["body", "title"])


def test_a_pull_request_without_a_record_is_not_touched(capsys: pytest.CaptureFixture[str]) -> None:
    api = FakeApi(changed={8679: files(RESOURCE)}, pulls={mirror.branch_name(8679): shoal_pull(7, "by hand")})
    changes, failed = mirror.sync(api, [pull()], NOTHING_LINKED, None, dry_run=False)
    assert (changes, failed) == ([], [])
    assert "#7 is on upstream/discord-api-docs-8679 but has no readable record" in capsys.readouterr().err


def test_reopening_and_removing_labels_go_through_the_api() -> None:
    existing = current(pull(), files(SOCIAL), is_open=False)
    change = planned(pull(head="def", merge="newer"), files(RESOURCE), existing)
    api = FakeApi(branches={change.branch: Branch("branch-head", owned=True, behind=0)})
    mirror.apply(change, api, "main-sha")
    assert api.calls == [
        ("edit_pull", 12, ["state"]),
        ("commit_files", "main-sha", ["discord-api-docs.lock"], "newer\n"),
        ("set_branch", "upstream/discord-api-docs-8679", "new-commit", False, True),
        ("comment", 12),
        ("add_labels", 12, ["payloads", "rest"]),
        ("remove_label", 12, "unrelated"),
        ("edit_pull", 12, ["body", "title"]),
    ]


def test_a_branch_someone_pushed_to_gets_a_commit_that_moves_only_the_pin() -> None:
    change = Change(upstream=8679, pull=12, title="t", body="b", pin="newer", coverage="REPORT", edit=False)
    api = FakeApi(
        branches={change.branch: Branch("theirs", owned=False, behind=3)}, locks={"theirs": "older"}
    )
    mirror.push_pin(api, change, "main-sha")
    assert api.calls == [
        ("commit_files", "theirs", ["discord-api-docs.lock"], "newer\n"),
        ("set_branch", "upstream/discord-api-docs-8679", "new-commit", False, False),
    ]
    api = FakeApi(
        branches={change.branch: Branch("theirs", owned=False, behind=3)}, locks={"theirs": "newer"}
    )
    mirror.push_pin(api, change, "main-sha")
    assert api.calls == []


def test_an_owned_branch_carries_the_coverage_report_for_its_pin() -> None:
    change = Change(upstream=8679, pull=None, title="t", body="b", pin="newer", coverage="REPORT")
    api = FakeApi()
    mirror.push_pin(api, change, "main-sha")
    assert api.calls[0] == (
        "commit_files",
        "main-sha",
        ["discord-api-docs.lock", "docs/coverage.md"],
        "newer\n",
    )


def test_branches_behind_main_are_rebuilt_while_only_the_mirror_owns_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    tracked = mirror.marker(Mirror(pr=8679, pin="pinned"))
    api = FakeApi(
        pulls={
            "owned": shoal_pull(1, tracked),
            "theirs": shoal_pull(2, tracked),
            "current": shoal_pull(3, tracked),
            "unpinned": shoal_pull(4, mirror.marker(Mirror(pr=8679))),
        },
        branches={
            "upstream/discord-api-docs-8679": Branch("b", owned=True, behind=2),
        },
    )
    api.pulls["owned"].head.ref = "upstream/discord-api-docs-8679"
    api.pulls["theirs"].head.ref = "theirs"
    api.branches["theirs"] = Branch("t", owned=False, behind=2)
    api.pulls["current"].head.ref = "current"
    api.branches["current"] = Branch("c", owned=True, behind=0)
    assert mirror.refresh(api, "main-sha", "main-pin", None, dry_run=True) == (1, [])
    assert api.calls == []
    assert "rebuild upstream/discord-api-docs-8679 (#1) on main" in capsys.readouterr().out
    assert mirror.refresh(api, "main-sha", "main-pin", None, dry_run=False) == (1, [])
    assert api.calls == [
        ("commit_files", "main-sha", ["discord-api-docs.lock"], "pinned\n"),
        ("set_branch", "upstream/discord-api-docs-8679", "new-commit", False, True),
    ]


def test_a_branch_main_already_pins_past_is_not_rebuilt(capsys: pytest.CaptureFixture[str]) -> None:
    api = FakeApi(
        pulls={"owned": shoal_pull(1, mirror.marker(Mirror(pr=8679, pin="pinned")))},
        branches={"upstream/discord-api-docs-8679": Branch("b", owned=True, behind=2)},
        contained=True,
    )
    assert mirror.refresh(api, "main-sha", "main-pin", None, dry_run=False) == (0, [])
    assert api.calls == []
    assert "main already pins past pinned" in capsys.readouterr().out


def test_a_branch_that_fails_to_rebuild_does_not_stop_the_run(capsys: pytest.CaptureFixture[str]) -> None:
    api = FakeApi(
        changed={1: files(RESOURCE)},
        pulls={"owned": shoal_pull(5, mirror.marker(Mirror(pr=8679, pin="gone")))},
        branches={"upstream/discord-api-docs-8679": Branch("b", owned=True, behind=2)},
    )
    docs = FakeCheckout({})
    docs.failing = True
    changes, failed = mirror.sync(api, [pull(1)], NOTHING_LINKED, docs, dry_run=False, pin="main-pin")
    assert failed == [8679, 1]
    assert changes == []
    assert "error: rebuilding upstream/discord-api-docs-8679 (#5)" in capsys.readouterr().err


def test_a_dry_run_changes_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    api = FakeApi(changed={1: files(RESOURCE), 2: files(RESOURCE)})
    changes, _ = mirror.sync(api, [pull(1), pull(2, state="closed")], NOTHING_LINKED, None, dry_run=True)
    assert [change.upstream for change in changes] == [1]
    assert api.calls == []
    assert "-> new pull request: docs#1" in capsys.readouterr().out


def test_a_pull_request_listed_twice_is_mirrored_once() -> None:
    api = FakeApi(changed={1: files(RESOURCE)})
    changes, _ = mirror.sync(api, [pull(1), pull(1)], NOTHING_LINKED, None, dry_run=False)
    assert len(changes) == 1
    assert [call[0] for call in api.calls].count("create_pull") == 1


def test_a_failing_pull_request_does_not_stop_the_others(capsys: pytest.CaptureFixture[str]) -> None:
    api = FakeApi(changed={2: files(RESOURCE)})
    changes, failed = mirror.sync(api, [pull(1), pull(2)], NOTHING_LINKED, None, dry_run=True)
    assert [change.upstream for change in changes] == [2]
    assert failed == [1]
    assert "error: discord/discord-api-docs#1: <urlopen error unreachable>" in capsys.readouterr().err


def test_the_docs_check_reports_against_main_pin_and_commits_the_coverage() -> None:
    api = FakeApi(changed={1: files(RESOURCE)})
    docs = FakeCheckout(
        {
            "main-pin": check((), "| yes | [Old](x) |\n"),
            "test-merge": check((), f"| no | [New]({MESSAGE_PAGE}#new) |\n"),
        }
    )
    [change], _ = mirror.sync(api, [pull(1)], NOTHING_LINKED, docs, dry_run=False)
    assert change.coverage == f"| no | [New]({MESSAGE_PAGE}#new) |\n"
    assert "### Docs check: `main-pin` to `test-merge`" in change.body
    assert f"+| no | [New]({MESSAGE_PAGE}#new) |" in change.body
    assert writes(api)[0][2] == ["discord-api-docs.lock", "docs/coverage.md"]


def git(*arguments: str, cwd: Path) -> str:
    result = subprocess.run(["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True)  # noqa: S603, S607  # fixed arguments
    return result.stdout.strip()


def test_the_docs_checkout_fetches_and_checks_each_revision_once(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git("init", "--quiet", cwd=upstream)
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=upstream)
    git("config", "uploadpack.allowFilter", "true", cwd=upstream)
    revisions: list[str] = []
    for text in ("first", "second"):
        (upstream / "page.mdx").write_text(text, encoding="utf-8")
        git("add", ".", cwd=upstream)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", text, cwd=upstream)
        revisions.append(git("rev-parse", "HEAD", cwd=upstream))
    seen: list[str] = []

    def checker(path: Path) -> DocsCheck:
        text = (path / "page.mdx").read_text(encoding="utf-8")
        seen.append(text)
        return check((), text)

    docs = mirror.DocsCheckout(tmp_path / "checkout", remote=upstream.as_uri(), checker=checker)
    assert docs.check(revisions[0]).coverage == "first"
    assert docs.check(revisions[1]).coverage == "second"
    assert docs.check(revisions[0]).coverage == "first"
    assert seen == ["first", "second"]


def test_main_needs_a_token_unless_listing_unmatched_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["mirror_upstream_prs.py", "--dry-run"])
    assert mirror.main() == 2
    monkeypatch.setattr(sys, "argv", ["mirror_upstream_prs.py", "--unmatched", str(tmp_path)])
    assert mirror.main() == 0
    (tmp_path / "new.mdx").write_text("x", encoding="utf-8")
    assert mirror.main() == 1
    assert "new.mdx" in capsys.readouterr().out


def test_unmatched_lists_paths_no_rule_covers(tmp_path: Path) -> None:
    for path in (
        "developers/resources/user.mdx",
        "developers/new/page.mdx",
        ".git/HEAD",
        "node_modules/x/y.js",
    ):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x", encoding="utf-8")
    assert mirror.unmatched(tmp_path) == ["developers/new/page.mdx"]


@dataclass
class Recorded:
    method: str
    path: str
    authorization: str | None
    body: bytes


@dataclass
class Routes:
    responses: dict[str, tuple[bytes, str]]
    requests: list[Recorded] = field(default_factory=list[Recorded])
    failures: dict[str, list[tuple[int, dict[str, str]]]] = field(
        default_factory=dict[str, list[tuple[int, dict[str, str]]]]
    )
    """Statuses (and headers) to answer a path with, in order, before its response."""


def serve(routes: Routes) -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def _respond(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            routes.requests.append(
                Recorded(self.command, self.path, self.headers.get("Authorization"), self.rfile.read(length))
            )
            if queued := routes.failures.get(self.path):
                status, headers = queued.pop(0)
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            content, link = routes.responses.get(self.path, (b"{}", ""))
            self.send_response(200)
            if link:
                self.send_header("Link", link.replace("BASE", base))
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_POST = do_PATCH = do_DELETE = _respond  # noqa: N815  # the names the base class calls

        @override
        def log_message(self, format: str, *args: object) -> None:  # the base class's name
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, base


type Fixture = tuple[mirror.GitHub, Routes, list[float]]
REPO = "/repos/relateful/shoal"
UPSTREAM_REPO = "/repos/discord/discord-api-docs"
FILES = f"{UPSTREAM_REPO}/pulls/7/files?per_page=100"


@pytest.fixture
def github() -> Iterator[Fixture]:
    routes = Routes({})
    server, base = serve(routes)
    pauses: list[float] = []
    try:
        yield mirror.GitHub("secret", "relateful/shoal", api=base, pause=pauses.append), routes, pauses
    finally:
        server.shutdown()
        server.server_close()


def encode_pulls(*numbers_and_times: tuple[int, str]) -> bytes:
    return msgspec.json.encode(
        [
            {
                "number": number,
                "title": "t",
                "html_url": "u",
                "state": "open",
                "updated_at": updated,
                "user": {"login": "someone"},
                "head": {"sha": "abc", "ref": "x"},
                "merged_at": None,
                "merge_commit_sha": "m",
            }
            for number, updated in numbers_and_times
        ]
    )


def encode_shoal_pulls(*numbers_and_refs: tuple[int, str]) -> bytes:
    return msgspec.json.encode(
        [
            {"number": number, "title": "t", "state": "open", "head": {"sha": "s", "ref": ref}, "labels": []}
            for number, ref in numbers_and_refs
        ]
    )


def test_the_client_follows_pages_and_stops_at_the_cutoff(github: Fixture) -> None:
    api, routes, _ = github
    first = f"{UPSTREAM_REPO}/pulls?state=all&sort=updated&direction=desc&per_page=100"
    routes.responses[first] = (
        encode_pulls((3, "2026-10-25T00:00:00Z")),
        '<BASE/page2>; rel="next", <BASE/last>; rel="last"',
    )
    routes.responses["/page2"] = (encode_pulls((2, "2026-10-24T00:00:00Z"), (1, "2026-10-01T00:00:00Z")), "")
    since = datetime(2026, 10, 20, tzinfo=UTC)
    assert [found.number for found in api.upstream_pulls(since)] == [3, 2]
    assert [request.path for request in routes.requests] == [first, "/page2"]
    assert {request.authorization for request in routes.requests} == {"Bearer secret"}


def test_the_client_reads_upstream(github: Fixture) -> None:
    api, routes, _ = github
    routes.responses[f"{UPSTREAM_REPO}/pulls/7"] = (encode_pulls((7, "2026-10-25T00:00:00Z"))[1:-1], "")
    routes.responses[FILES] = (b'[{"filename": "a", "status": "added", "additions": 1, "deletions": 0}]', "")
    compare = f"{UPSTREAM_REPO}/compare/commit...revision?per_page=1"
    routes.responses[compare] = (b'{"status": "ahead", "behind_by": 0, "commits": []}', "")
    assert api.upstream_pull(7).number == 7
    assert [changed.filename for changed in api.pull_files(7)] == ["a"]
    assert api.upstream_contains("revision", "commit")
    routes.responses[compare] = (b'{"status": "diverged", "behind_by": 2, "commits": []}', "")
    assert not api.upstream_contains("revision", "commit")


def test_the_client_reads_shoal(github: Fixture) -> None:
    api, routes, _ = github
    head = "relateful%3Aupstream%2Fdiscord-api-docs-7"
    routes.responses[f"{REPO}/pulls?head={head}&state=all&per_page=100"] = (
        encode_shoal_pulls((3, "upstream/discord-api-docs-7"), (9, "upstream/discord-api-docs-7")),
        "",
    )
    routes.responses[f"{REPO}/pulls?state=open&per_page=100"] = (
        encode_shoal_pulls((9, "upstream/discord-api-docs-7"), (10, "feature")),
        "",
    )
    routes.responses[f"{REPO}/git/ref/heads/main"] = (b'{"object": {"sha": "main-sha"}}', "")
    routes.responses[f"{REPO}/contents/discord-api-docs.lock?ref=main-sha"] = (b'{"content": "cGluCg=="}', "")
    routes.failures[f"{REPO}/contents/discord-api-docs.lock?ref=old"] = [(404, {})]
    routes.responses[f"{REPO}/labels?per_page=100"] = (b'[{"name": "bug"}]', "")
    runs = f"{REPO}/actions/workflows/upstream-docs.yml/runs?event=schedule&status=success&per_page=1"
    routes.responses[runs] = (b'{"workflow_runs": [{"created_at": "2026-10-25T10:00:00Z"}]}', "")
    found = api.find_pull("upstream/discord-api-docs-7")
    assert found is not None
    assert found.number == 9
    assert [entry.number for entry in api.open_pulls()] == [9]
    assert api.main_head() == "main-sha"
    assert api.read_lock("main-sha") == "pin"
    assert api.read_lock("old") is None
    assert api.labels() == {"bug"}
    assert api.last_success("upstream-docs.yml") == datetime(2026, 10, 25, 10, tzinfo=UTC)
    routes.responses[runs] = (b'{"workflow_runs": []}', "")
    assert api.last_success("upstream-docs.yml") is None


def test_the_client_reads_who_owns_a_branch(github: Fixture) -> None:
    api, routes, _ = github
    routes.responses[f"{REPO}/git/ref/heads/mine"] = (b'{"object": {"sha": "m1"}}', "")
    mirror_commit = {"commit": {"author": {"email": mirror.COMMIT_AUTHOR["email"]}}}
    routes.responses[f"{REPO}/compare/main...m1"] = (
        msgspec.json.encode({"status": "diverged", "behind_by": 4, "commits": [mirror_commit]}),
        "",
    )
    routes.responses[f"{REPO}/git/ref/heads/theirs"] = (b'{"object": {"sha": "t1"}}', "")
    person = {"commit": {"author": {"email": "someone@example.com"}}}
    routes.responses[f"{REPO}/compare/main...t1"] = (
        msgspec.json.encode({"status": "ahead", "behind_by": 0, "commits": [mirror_commit, person]}),
        "",
    )
    routes.failures[f"{REPO}/git/ref/heads/gone"] = [(404, {})]
    assert api.branch("mine") == Branch("m1", owned=True, behind=4)
    assert api.branch("theirs") == Branch("t1", owned=False, behind=0)
    assert api.branch("gone") is None


def test_the_client_commits_and_moves_branches(github: Fixture) -> None:
    api, routes, pauses = github
    routes.responses[f"{REPO}/git/commits/parent"] = (b'{"sha": "parent", "tree": {"sha": "base-tree"}}', "")
    routes.responses[f"{REPO}/git/trees"] = (b'{"sha": "tree"}', "")
    routes.responses[f"{REPO}/git/commits"] = (b'{"sha": "commit"}', "")
    assert api.commit_files("parent", {"discord-api-docs.lock": "pin\n"}, "message") == "commit"
    api.set_branch("upstream/x", "commit", create=True, force=True)
    api.set_branch("upstream/x", "commit", create=False, force=False)
    assert [(request.method, request.path) for request in routes.requests] == [
        ("GET", f"{REPO}/git/commits/parent"),
        ("POST", f"{REPO}/git/trees"),
        ("POST", f"{REPO}/git/commits"),
        ("POST", f"{REPO}/git/refs"),
        ("PATCH", f"{REPO}/git/refs/heads/upstream/x"),
    ]
    bodies = [msgspec.json.decode(request.body) for request in routes.requests[1:]]
    assert bodies == [
        {
            "base_tree": "base-tree",
            "tree": [{"path": "discord-api-docs.lock", "mode": "100644", "type": "blob", "content": "pin\n"}],
        },
        {"message": "message", "tree": "tree", "parents": ["parent"], "author": mirror.COMMIT_AUTHOR},
        {"ref": "refs/heads/upstream/x", "sha": "commit"},
        {"sha": "commit", "force": False},
    ]
    assert pauses == [mirror.WRITE_PAUSE] * 4


def test_the_client_writes_pull_requests_and_pauses_after_each_write(github: Fixture) -> None:
    api, routes, pauses = github
    routes.responses[f"{REPO}/pulls"] = (encode_shoal_pulls((41, "b"))[1:-1], "")
    assert api.create_pull("t", "b", "upstream/x") == 41
    api.edit_pull(41, {"state": "open"})
    api.comment(41, "hello")
    api.add_labels(41, ["rest"])
    api.remove_label(41, "needs triage")
    api.create_label("rest", "006b75", "d")
    assert [(request.method, request.path) for request in routes.requests] == [
        ("POST", f"{REPO}/pulls"),
        ("PATCH", f"{REPO}/pulls/41"),
        ("POST", f"{REPO}/issues/41/comments"),
        ("POST", f"{REPO}/issues/41/labels"),
        ("DELETE", f"{REPO}/issues/41/labels/needs%20triage"),
        ("POST", f"{REPO}/labels"),
    ]
    assert msgspec.json.decode(routes.requests[0].body) == {
        "title": "t",
        "body": "b",
        "head": "upstream/x",
        "base": "main",
    }
    assert pauses == [mirror.WRITE_PAUSE] * 6


def test_the_client_retries_rate_limits_and_server_errors(github: Fixture) -> None:
    api, routes, pauses = github
    routes.responses[FILES] = (b"[]", "")
    routes.failures[FILES] = [(429, {"Retry-After": "7"}), (502, {})]
    assert api.pull_files(7) == []
    assert pauses == [7.0, mirror.RETRY_DELAY]


def test_the_client_gives_up_when_retrying_cannot_help(github: Fixture) -> None:
    api, routes, pauses = github
    routes.failures[FILES] = [(403, {})]
    with pytest.raises(urllib.error.HTTPError) as failure:
        api.pull_files(7)
    failure.value.close()
    routes.failures[FILES] = [(500, {})] * mirror.RETRIES
    with pytest.raises(urllib.error.HTTPError) as failure:
        api.pull_files(7)
    failure.value.close()
    routes.failures[f"{REPO}/git/ref/heads/broken"] = [(500, {})] * mirror.RETRIES
    with pytest.raises(urllib.error.HTTPError) as failure:
        api.branch("broken")
    failure.value.close()
    assert pauses == [mirror.RETRY_DELAY] * (mirror.RETRIES - 1) * 2


def test_the_client_waits_for_an_exhausted_rate_limit(github: Fixture) -> None:
    api, routes, pauses = github
    routes.responses[FILES] = (b"[]", "")
    reset = str(int(time.time()) + 10_000)
    routes.failures[FILES] = [(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset})]
    api.pull_files(7)
    assert pauses == [mirror.MAX_RETRY_DELAY]


def test_removing_a_label_that_is_already_gone_succeeds(github: Fixture) -> None:
    api, routes, _ = github
    path = f"{REPO}/issues/41/labels/rest"
    routes.failures[path] = [(404, {})]
    api.remove_label(41, "rest")
    routes.failures[path] = [(422, {})]
    with pytest.raises(urllib.error.HTTPError) as failure:
        api.remove_label(41, "rest")
    failure.value.close()
