# Contributing to Shoal

These are the project's rules. Most are enforced: by ruff, by pyright and mypy in strict mode, by
`import-linter`, and by `tests/conventions.py`, which checks the rules a linter cannot express across
the whole tree. If a rule here is not enforced yet, enforcing it is a welcome contribution.

## Setup

```bash
uv sync --all-groups
```

Every check CI runs:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run mypy
uv run lint-imports
uv run python scripts/sort_constants.py --check
uv run python scripts/generate_exports.py --check
uv run pytest --cov
uv run mkdocs build --strict
git init ../discord-api-docs
git -C ../discord-api-docs fetch --depth 1 https://github.com/discord/discord-api-docs "$(cat discord-api-docs.lock)"
git -C ../discord-api-docs checkout --detach FETCH_HEAD
uv run python scripts/check_docs.py --docs-repo ../discord-api-docs --check-coverage docs/coverage.md
```

## Layout and layers

```
src/shoal/
  core/          primitives: snowflakes, flags, open enums, codec, clock, tasks, private files,
                 metrics catalog, dispatch event, Ogg reading and writing
  payloads/      one module per Discord domain (user, guild, channel, message, gateway, ...)
  rest/          HTTP client, routes, rate limiting, the REST proxy
  gateway/       shards, sessions, compression, clusters
  cache/         cache store and updater
  ipc/           gateway-to-worker transport
  metrics/       exporters (Prometheus)
  diagnostics/   event loop health
  endpoint/      interactions over HTTP, for bots without a gateway
  tasks/         background loops, cron, and scheduled jobs that survive restarts
  redis/         state shared by a bot's processes in Redis: rate limits, identify, sessions, cache,
                 events, the shard directory, command routing and scheduled jobs
  voice/         voice connections: the voice gateway, UDP, transport encryption, DAVE and audio
  models/        objects with methods (Guild, Member, Message, ...) over a cache and a REST client
  emojis/        the application's emojis: a registry used across the bot, and a sync from a folder
  client/        Client: events as models, interactions, views and modals waiting for answers
  ui/            views, buttons, selects and modals
  app_commands/  slash commands, context menus, the command tree and its checks
  commands/      prefix and hybrid commands, Bot, cogs, converters, extensions, help
  compat/        familiar names for migrating bots (error names without Error), and their helpers
tests/           mirrors src/shoal/: tests/rest/route.py tests src/shoal/rest/route.py
scripts/         maintenance scripts (docs checker, export generator, constant sorter, upstream mirror)
docs/            guides and the home page; the API reference is generated from docstrings
theme/           the docs site's own theme: templates, styles and scripts, no third-party theme
```

`core` depends on nothing but the standard library and msgspec. `payloads` depends on `core`. The
transport layers (`rest`, `gateway`, `cache`, `ipc`, `metrics`, `diagnostics`, `endpoint`, `tasks`) depend on
`core` and `payloads` and **never on each other**, so each can run in its own process. `redis`
implements their extension points (limiters, session store, cache collections, event transport,
shard directory, command router, job store), and `voice` builds voice connections on the gateway's websocket;
both sit above them, beside each other. Above them the bot layers stack in this order, each using
only those below it: `models`, `emojis`, `client`, then `ui` and `app_commands` (beside each other),
then `commands`, then `compat` (aliases over the rest, for migrating bots; nothing imports it).
`import-linter` enforces this, and `tests/conventions.py` checks that every package is named here
and in the contract.

## Where things go

| Adding | Goes in |
| --- | --- |
| A Discord JSON object | `payloads/<domain>.py` |
| A constant Discord documents | next to its types in `payloads/<domain>.py` |
| A Shoal default (timeout, threshold, size) | `<layer>/defaults.py` |
| An HTTP endpoint | a `Route` in `rest/endpoints.py`, a method on the resource's class in `rest/resources/<resource>.py` (named per [Naming](#naming)), and an `EndpointCase` in `tests/rest/resources/<resource>.py` |
| A metric | `core/metrics.py`, recorded where the event happens |
| A test for `src/shoal/<layer>/<module>.py` | `tests/<layer>/<module>.py` |
| A helper shared by tests | `tests/support/` |

Every constant is defined once. Import it; never redefine it.

## Naming

Names are short, predictable and the same everywhere. When a concept exists in discord.py, use
discord.py's name for it (`send_message`, `defer`, `followup`, `get_member`, `ephemeral`), so a
migrating bot changes its imports and little else.

**REST.** Endpoints are grouped by the resource they act on, as attributes of `RestClient`:
`rest.<resource>.<verb>(...)`. The attribute is the class name in snake case (`Messages` is
`rest.messages`, `ScheduledEvents` is `rest.scheduled_events`); a test enforces it.

| Verb | For |
| --- | --- |
| `get` | one object |
| `list` | many objects (paged or not) |
| `create`, `edit`, `delete` | never `modify`, `update` or `remove_x` for the resource itself |
| `add_x`, `remove_x` | linking something to the resource (`members.add_role`, `threads.remove_member`) |
| `overwrite` | replacing a whole set at once (`commands.overwrite_global`) |
| a domain verb | when Discord's action has one: `ban`, `unban`, `kick`, `pin`, `crosspost`, `prune`, `sync`, `execute`, `respond`, `follow`, `typing`, `end` |

- The current user or app is `me` (`users.get_me`, `members.edit_me`); something it owns is `my`
  (`members.edit_my_nick`, `reactions.remove_mine`).
- Commands exist at two scopes and name both: `list_global`, `list_guild`. Elsewhere the guild is
  the default scope and another scope is a suffix: `webhooks.list_for_channel`,
  `emojis.create_for_application`.
- A qualifier follows the verb: `list_bans`, `get_member_counts`, `edit_positions`.
- Resource classes name a method `list`, so their signatures write the builtin as `builtins.list`.

**Parameter structs** are named after the method that takes them: `<Verb><Thing>Params`
(`EditMemberParams` for `members.edit`, `BanParams` for `members.ban`). Where the current user is
meant, the struct says `Current` (`EditCurrentUserParams`), as Discord's docs do.

**Payloads** keep the name of the Discord object they mirror (`GuildMember`, `StageInstance`); a
gateway event's body is named after the event (`GuildBanAdd` for `GUILD_BAN_ADD`).

## Discord documentation links

- Every Discord type, enum, flag set, documented constant and gateway event links to the section
  that documents it, as the last line of its docstring:
  `Discord: https://docs.discord.com/developers/resources/user#user-object`. A `Route` carries its
  link in `docs=`, and the resource method that calls it repeats the link in its docstring.
- Links use `https://docs.discord.com/developers/` and point at the narrowest section that exists.
- `scripts/check_docs.py` verifies every link and anchor against the Discord docs source, and every
  `Route`'s method and path against Discord's `<Route>` declaration. CI runs it on every change,
  against the docs revision `discord-api-docs.lock` pins, and checks that the revision is on
  Discord's main branch. The weekly coverage workflow compares against Discord's latest docs.
- `docs/coverage.md` is generated and lists every documented endpoint with whether Shoal implements
  it. Every endpoint is implemented except the ones Discord has deprecated (marked in the heading)
  or disabled (`DISABLED_ROUTES` in `scripts/check_docs.py`), which are marked and not counted.

### Upstream docs changes

Every pull request on [discord/discord-api-docs](https://github.com/discord/discord-api-docs) that
touches the API Shoal models gets a pull request here, so a change to the API is noticed, checked
and implemented before it ships. `.github/workflows/upstream-docs.yml` runs
`scripts/mirror_upstream_prs.py` hourly (Discord's webhooks cannot reach another organisation's
repository, so it polls), looking back to an hour before its last successful scheduled run (24 hours
on the first run, and never more than seven days). A failed run does not move that point, so the next
one tries again; manual runs never move it. A pull request that fails is reported and the others
carry on, and the run then fails.

- **What a mirror pull request changes.** Its branch, `upstream/discord-api-docs-<number>`, moves
  `discord-api-docs.lock` to the upstream change and regenerates `docs/coverage.md` for it, so CI
  checks Shoal against the change. While upstream is open the pin is GitHub's test merge of the
  change into Discord's main branch (its head commit if it conflicts), and the "pinned revision is on
  Discord's main branch" check fails, so it cannot be merged early; once upstream merges, the pin
  moves to the merge commit. Push the Shoal changes the update needs to the same branch, then merge.
- **The body** links the upstream pull request and each changed file's diff, and reports what
  `scripts/check_docs.py` finds against the new revision that it did not against the one `main`
  pins: new or fixed problems and endpoint or event coverage, limited to the pages the change
  touches. It ends with a hidden record (upstream number, head, state, verdict, pin) that later runs
  read, and is rewritten as upstream moves, so discuss in comments. The report is not committed:
  the body keeps it current, and committed reports would pile up and conflict.
- **Triage by path.** `RULES` in the script maps each docs path to the areas of Shoal it feeds, which
  become labels (`payloads`, `rest`, `gateway`, `interactions`, `ui`, `voice`, `changelog`), or to
  nothing for pages a bot library has no use for (Social SDK, Activities, Embedded App and Game
  SDKs, Rich Presence, guides, policies, the site's own assets). A change that is entirely unrelated
  gets no pull request; one that becomes unrelated after new commits is closed with the `unrelated`
  label. A path no rule covers, an unrelated page that Shoal links to, or a change to the change log
  alone gets a pull request labelled `needs-triage`. Nothing is opened for a change closed without
  merging, or for a merged one that the revision `main` pins already includes.
- **Updates.** A merge adds `upstream-merged` and a comment; a close without merging closes the pull
  request, and so does a merge that the revision `main` pins already includes (reopen it if its
  branch carries Shoal changes, taking `main`'s pin and coverage report). Runs act only on what
  changed upstream since the record, so a pull request you close or reopen, or a label you remove,
  stays as you left it. The record is written last, so a run that fails part way is redone by the
  next, which may repeat a comment but never loses one.
- **Branches.** Every mirror branch changes the same pin, so while a branch holds only the mirror's
  commits it is rebuilt on `main` whenever `main` moves, and stays mergeable, unless `main` already
  pins past it. Once you push to it, the mirror never rewrites it: it only adds commits that move the
  pin, and you regenerate `docs/coverage.md` (CI says when it is stale). The branch of a closed pull
  request is left alone, since GitHub cannot reopen a pull request whose branch was rewritten.
- **A token that starts CI.** Pull requests and pushes made with the workflow's `GITHUB_TOKEN` do not
  trigger other workflows, so CI would not run on mirror pull requests. Create a GitHub App owned by
  the repository's owner with repository permissions Contents, Pull requests, Issues and Workflows
  (read and write; Workflows because a branch rebuilt on `main` takes in `main`'s changes to
  `.github/workflows`) and Actions (read), install it on this repository only, then add its client
  ID as the
  Actions variable `UPSTREAM_DOCS_APP_CLIENT_ID` and a private key as the secret
  `UPSTREAM_DOCS_APP_PRIVATE_KEY`. The workflow uses the App's token when the variable is set, and
  warns and falls back to `GITHUB_TOKEN` when it is not. A fine-grained personal access token with the
  same permissions works too, but acts as a person and expires; the App is preferred.
- **Changing the rules.** Edit `RULES` and its tests in `tests/scripts/mirror_upstream_prs.py`. The
  weekly coverage workflow fails when the docs gain a path no rule covers;
  `--unmatched ../discord-api-docs` lists them locally. To preview a run, or to backfill, with the
  docs check run in a checkout the script may move freely (`--pin` stands in for the revision `main`
  pins, before it pins one):

```bash
export GITHUB_TOKEN=$(gh auth token)
uv run python scripts/mirror_upstream_prs.py --since-hours 72 --docs-repo ../docs-mirror --dry-run
```

## Payloads

Payloads mirror Discord's JSON exactly and hold data only.

| Discord docs | Meaning | Annotation |
| --- | --- | --- |
| `field: type` | always present | `field: T` |
| `field: ?type` | present, may be null | `field: T \| None` |
| `field?: type` | may be absent | `field: T \| UnsetType = UNSET` |
| `field?: ?type` | may be absent or null | `field: T \| UnsetType \| None = UNSET` |

- Fields keep the order of Discord's field table, so the class reads side by side with the docs.
- Snowflakes are `Snowflake`; bitfields are `BaseFlags` subclasses; enums are `DiscordIntEnum` or
  `DiscordStrEnum`, which accept values Discord adds later.
- A field whose type is not modeled yet is left out (msgspec ignores unknown keys) and listed in the
  module docstring under "Not yet modeled". Never type it as `Any` or `dict`; the one exception is
  JSON kept as received on purpose (see Typing).
- Subclasses that share fields through a private base (`_InteractionCommon`) list the shared fields
  first, so a field the subclass adds, such as `data`, comes last rather than in table order.
- When a Discord example omits a field its table requires, follow the table.
- After adding a payload, run `scripts/generate_exports.py`.

## Typing

- pyright and mypy run in strict mode over `src`, `tests` and `scripts`.
- `Any` is banned (ruff rule). Use `object`, a `Protocol`, a `TypeGuard` or a precise type. The one
  exception is `core.codec.JSONObject`, for JSON Discord extends faster than Shoal models it: received
  components (named `RawComponent` where they appear) and the body of an `UnknownInteraction` or
  `UnknownComponent`. It is converted to typed payloads before use. Two objects are kept as JSON
  because they have no fixed shape at all: a guild template's snapshot (placeholder integer IDs)
  and an identity profile's `metadata` (the game's own data). Aliases may rename `JSONObject`, but
  no other alias may wrap `Any`. Tests use it for JSON fixtures.
- A payload holding a credential (a token, an OAuth2 access token, a lobby secret) or an email
  address names it in `REDACTED_FIELDS`, so its repr never shows it; any other struct with such a
  field writes its own `__repr__`. A conventions test fails on a field named `*token`, `*secret`,
  `*password` or `*email` that a repr would show. Path parameters that grant access (tokens, invite
  and template codes) are in `rest.route.SECRET_PARAMETERS`, which keeps them out of logs.
- A value whose type depends on another field, like an audit log change's `old_value` and
  `new_value`, is `msgspec.Raw`: the caller decodes it into the type the other field names.
- `cast` and `type: ignore` are a last resort. Say why on the same line or the line above (a
  conventions test checks every cast); a `type: ignore` also names its error code.
- Use Python 3.12 syntax: `type` aliases, `class Box[T]`, `def first[T]`.
- Protocols describe every swappable dependency (transport, connector, clock, rate limiter, identify
  limiter, session store, cache collection, metrics).

## Ordering

So that anything can be found without searching:

- enum members and flags in value order, which is also the order of Discord's tables;
- string enum members alphabetically by value;
- module constants alphabetically, with an `ALL_*` aggregate last (`scripts/sort_constants.py`);
- dispatch tables, the metric catalog and `__all__` alphabetically.

## Code style

- Names say what things are; no abbreviations beyond Discord's own (`id`, `url`) and the `msg` local
  that ruff's exception-message rule expects.
- Docstrings explain behaviour and reasons (Google style). Comments are rare and explain why, never
  what. No section-banner comments (`# Login ------`); a module that needs them should be split.
- Code, comments, docstrings and tests describe Shoal on its own terms and never mention other
  Discord libraries. Only what compares directly names discord.py: the README, the migration guide
  and the `compat` example (a discord.py bot moved over) with its entry in the examples index.
  A dependency (aiohttp, redis-py) may be named where its behaviour is the reason for the code.
- No unreachable or defensive dead code: pyright reports code that narrowing makes unreachable
  (`enableReachabilityAnalysis`), and a branch that cannot happen is removed, not kept "just in case".
- Classes declare `__slots__`; dataclasses use `slots=True`.
- Exception names end in `Error` and every Shoal exception derives from `ShoalError`.
- Nothing blocks the event loop: file I/O goes through `asyncio.to_thread`, and CPU-heavy work does
  not run on the loop.
- Nothing fails silently: anything dropped, retried or rate limited is logged and counted in a metric.
- Absent values: payloads use msgspec's `UNSET` for a field Discord left out (`None` is Discord's
  `null`). Model `edit(...)` keywords default to `MISSING`, "leave as it is", so `None` can mean
  "clear it"; `models.base.given` turns `MISSING` into `UNSET` for the request. Model `create(...)`
  keywords default to `None`, since there is nothing to keep.
- Everything that schedules or measures a delay takes a `Clock`, so tests never sleep for real: wait
  with `clock.sleep`, bound a wait with `core.clock.within`, tell the time with `clock.wall()` (models:
  `state.now()`). Two exceptions: `LoopMonitor`, whose job is to measure the real event loop, and the
  connect and handshake timeouts of the network adapters (`gateway.connection`, `ipc`), which wait on
  real sockets. `tests/conventions.py` enforces it.
- Every queue, cache and buffer is bounded: by an explicit limit, or by mirroring state Discord
  bounds (a guild's members, channels and roles). Anything that grows with traffic (messages, users
  seen as message authors, IPC queues) has a limit.

## Tests

- Every module with behaviour has a test module at the mirrored path; `tests/conventions.py` enforces it.
- Test modules are named after the module they test, without a `test_` prefix. Test functions keep it.
- Tests never touch the network or Discord. Adapters are tested against local servers on loopback.
- Time is controlled with `tests/support/fakes.py` (`FakeClock`, `ManualClock`), not with sleeps.
- Coverage stays above 95%.
- When a test encodes wrong behaviour, fix the test.

## Commits

Conventional Commits: `type(scope): subject`, imperative and lower case. Scopes are the packages
(`core`, `payloads`, `rest`, `gateway`, `cache`, `ipc`, `metrics`, `diagnostics`, `endpoint`,
`tasks`, `redis`, `voice`, `models`, `emojis`, `client`, `ui`, `app_commands`, `commands`, `compat`) plus `docs`, `ci`
and `build`. Update
`CHANGELOG.md` under "Unreleased".

## Pull requests

Every change reaches `main` through a pull request; nothing is pushed to `main` directly.

- **One purpose per pull request.** A fix found along the way (a flaky test, an unrelated bug) gets
  its own pull request, not an extra commit in the current one.
- **Branches** are named `<type>/<short-topic>` with the commit types above: `feat/voice-receive`,
  `fix/ci-cross-platform`, `ci/release-workflow`, `docs/pull-request-rules`.
- **The title** is the Conventional Commit subject the squashed commit will carry.
- **The description** fills in `.github/PULL_REQUEST_TEMPLATE.md`. "What and why" names the problem
  first; when a pull request fixes several things, a table gives each one's failure, cause and fix.
  "Discord docs" links every Discord section the change implements, or says "None" and why. Tick a
  checklist item only once it is true.
- **CI must pass on the latest commit**, on every platform. A failure is diagnosed from its log,
  never rerun until it happens to pass: a flaky test is a bug, fixed in its own pull request.
- **Before merging, the branch includes the latest `main`.** When another pull request merges first,
  merge `main` into the branch and let CI run again, so what is merged is what was tested.
- **Squash-merge** with the title as the subject (GitHub adds the number), then delete the branch.
  Merge in dependency order: a pull request that others build on goes first.
- Stage files by name, never `git add -A`: local and generated files stay out of every commit.

## Releases

Shoal is published to PyPI by `.github/workflows/release.yml` through trusted publishing; no token
is stored. To release `X.Y.Z`:

1. In a pull request, set `__version__` in `src/shoal/_version.py` to `X.Y.Z` and move the
   "Unreleased" entries of `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`. Merge it.
2. Tag the merge commit on `main` and push the tag: `git tag vX.Y.Z` then `git push origin vX.Y.Z`.
3. The workflow checks the tag matches the version, is on `main` and has a changelog section, runs
   the tests, builds, waits for approval in the `pypi` environment, publishes, and creates the
   GitHub release with that section as its notes (`scripts/release_notes.py`).

PyPI never accepts the same version twice, even after a deletion: a broken release is fixed with a
new version. Pre-releases (`X.Y.ZaN`, `bN`, `rcN`) are marked as such on GitHub.
