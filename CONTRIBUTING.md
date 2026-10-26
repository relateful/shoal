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
git clone --depth 1 https://github.com/discord/discord-api-docs ../discord-api-docs
uv run python scripts/check_docs.py --docs-repo ../discord-api-docs
```

## Layout and layers

```
src/shoal/
  core/          primitives: snowflakes, flags, open enums, codec, clock, tasks, private files,
                 metrics catalog, dispatch event
  payloads/      one module per Discord domain (user, guild, channel, message, gateway, ...)
  rest/          HTTP client, routes, rate limiting
  gateway/       shards, sessions, compression, clusters
  cache/         cache store and updater
  ipc/           gateway-to-worker transport
  metrics/       exporters (Prometheus)
  diagnostics/   event loop health
  interaction_server/  interactions over HTTP, for bots without a gateway
tests/           mirrors src/shoal/: tests/rest/route.py tests src/shoal/rest/route.py
scripts/         maintenance scripts (docs checker, export generator, constant sorter)
docs/            guides and the home page; the API reference is generated from docstrings
theme/           the docs site's own theme: templates, styles and scripts, no third-party theme
```

`core` depends on nothing but the standard library and msgspec. `payloads` depends on `core`. The
remaining layers depend on `core` and `payloads` and **never on each other**, so each can run in its
own process. `import-linter` enforces this.

## Where things go

| Adding | Goes in |
| --- | --- |
| A Discord JSON object | `payloads/<domain>.py` |
| A constant Discord documents | next to its types in `payloads/<domain>.py` |
| A Shoal default (timeout, threshold, size) | `<layer>/defaults.py` |
| An HTTP endpoint | a `Route` in `rest/endpoints.py`, a method in `rest/resources/<resource>.py`, and an `EndpointCase` in `tests/rest/resources/<resource>.py` |
| A metric | `core/metrics.py`, recorded where the event happens |
| A test for `src/shoal/<layer>/<module>.py` | `tests/<layer>/<module>.py` |
| A helper shared by tests | `tests/support/` |

Every constant is defined once. Import it; never redefine it.

## Discord documentation links

- Every Discord type, enum, flag set, documented constant and gateway event links to the section
  that documents it, as the last line of its docstring:
  `Discord: https://docs.discord.com/developers/resources/user#user-object`. A `Route` carries its
  link in `docs=`, and the `RestClient` method that calls it repeats the link in its docstring.
- Links use `https://docs.discord.com/developers/` and point at the narrowest section that exists.
- `scripts/check_docs.py` verifies every link and anchor against the Discord docs source, and every
  `Route`'s method and path against Discord's `<Route>` declaration. CI runs it on every change.
- `docs/coverage.md` is generated and lists every documented endpoint Shoal does not implement yet.

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
  `UnknownComponent`. It is converted to typed payloads before use. Aliases may rename
  `JSONObject`, but no other alias may wrap `Any`. Tests use it for JSON fixtures.
- `cast` and `type: ignore` are a last resort: name the error code and say why on the same line.
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
  what.
- Classes declare `__slots__`; dataclasses use `slots=True`.
- Exception names end in `Error` and every Shoal exception derives from `ShoalError`.
- Nothing blocks the event loop: file I/O goes through `asyncio.to_thread`, and CPU-heavy work does
  not run on the loop.
- Nothing fails silently: anything dropped, retried or rate limited is logged and counted in a metric.
- Everything that schedules or measures a delay takes a `Clock`, so tests never sleep for real. The one
  exception is `LoopMonitor`, whose job is to measure the real event loop.
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

Conventional Commits: `type(scope): subject`, imperative and lower case. Scopes are the layers (`core`,
`payloads`, `rest`, `gateway`, `cache`, `ipc`, `metrics`, `diagnostics`, `interaction_server`) plus `docs`, `ci` and
`build`. Update `CHANGELOG.md` under "Unreleased".
