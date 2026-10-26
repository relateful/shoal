"""Keeping the application's emojis in step with a folder of images.

    report = await sync_emojis(rest, application_id, Path("assets/emojis"))
    print(report)

Each image's file name is its emoji's name (`approve.png` is `:approve:`); subfolders only organise.
The sync lists the application's emojis first, then creates the missing ones and replaces those
whose image changed. A manifest next to the images records each emoji's ID and fingerprint, per
application, so unchanged emojis are skipped. An emoji Discord has but the manifest does not know
(the manifest is new, or was lost) is adopted as it is rather than uploaded again, so a lost
manifest never replaces every emoji; `replace_unknown=True` replaces them instead.

Emojis without an image in the folder are left alone unless `prune=True`. Uploads go one at a time
through the REST client's rate limiting; anything that fails for a temporary reason is tried again
in later rounds, and the report lists what still failed and why. Discord cannot change an emoji's
image, so replacing one deletes it and creates it again (with a new ID); if the upload then fails,
the emoji stays missing until the next sync creates it.

Discord: https://docs.discord.com/developers/resources/emoji#create-application-emoji
"""

import asyncio
import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import override

import msgspec

from shoal.core.clock import Clock, SystemClock
from shoal.core.files import write_private
from shoal.core.snowflake import Snowflake
from shoal.emojis.defaults import IMAGE_SUFFIXES, MANIFEST_NAME, SYNC_ROUND_PAUSE, SYNC_ROUNDS
from shoal.payloads.emoji import (
    APPLICATION_MAX_EMOJIS,
    EMOJI_MAX_SIZE,
    CreateApplicationEmojiParams,
    Emoji,
    emoji_content_type,
    emoji_data,
)
from shoal.rest.client import RestClient
from shoal.rest.errors import BadRequestError, HTTPError, ServerError
from shoal.rest.transport import TransportError

_log = logging.getLogger("shoal.emojis")


@dataclass(frozen=True, slots=True)
class LocalEmoji:
    """An image in the emoji folder."""

    name: str
    path: Path
    sha256: str
    """The image's fingerprint, to tell a changed image from an unchanged one."""


class ManifestEntry(msgspec.Struct, frozen=True):
    """What the manifest records about one uploaded emoji."""

    id: int
    sha256: str


class Manifest(msgspec.Struct):
    """Uploaded emojis by application ID (as a string, JSON's only key type), then by name."""

    applications: dict[str, dict[str, ManifestEntry]] = msgspec.field(
        default_factory=dict[str, dict[str, ManifestEntry]]
    )


@dataclass(slots=True)
class SyncReport:
    """What a sync did, or with `dry_run`, would do."""

    dry_run: bool = False
    created: list[str] = field(default_factory=list[str])
    replaced: list[str] = field(default_factory=list[str])
    unchanged: list[str] = field(default_factory=list[str])
    adopted: list[str] = field(default_factory=list[str])
    """Emojis Discord had that the manifest did not know; recorded as they are."""
    deleted: list[str] = field(default_factory=list[str])
    unmanaged: list[str] = field(default_factory=list[str])
    """Emojis Discord has without an image in the folder, left alone (pass `prune=True` to delete)."""
    failed: dict[str, str] = field(default_factory=dict[str, str])
    """Emojis that could not be synced, with the reason."""

    @property
    def ok(self) -> bool:
        """Whether nothing failed."""
        return not self.failed

    @override
    def __str__(self) -> str:
        counts = [
            ("created", self.created),
            ("replaced", self.replaced),
            ("unchanged", self.unchanged),
            ("adopted", self.adopted),
            ("deleted", self.deleted),
            ("left alone", self.unmanaged),
        ]
        lead = "would sync (dry run)" if self.dry_run else "synced"
        summary = ", ".join(f"{len(names)} {label}" for label, names in counts if names) or "nothing to do"
        lines = [f"{lead}: {summary}"]
        lines.extend(f"failed {name}: {reason}" for name, reason in sorted(self.failed.items()))
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class _Remote:
    """An emoji the application has: its name and ID."""

    name: str
    id: Snowflake


@dataclass(frozen=True, slots=True)
class _Plan:
    create: list[LocalEmoji]
    replace: list[tuple[LocalEmoji, _Remote]]
    delete: list[_Remote]


async def sync_emojis(
    rest: RestClient,
    application_id: int,
    folder: Path,
    *,
    manifest: Path | None = None,
    prune: bool = False,
    replace_unknown: bool = False,
    dry_run: bool = False,
    rounds: int = SYNC_ROUNDS,
    clock: Clock | None = None,
) -> SyncReport:
    """Make application `application_id`'s emojis match the images in `folder`.

    Args:
        rest: The REST client, with the application's bot token.
        application_id: The application whose emojis to sync.
        folder: The images, searched recursively; each file's name (without suffix) is the emoji's.
        manifest: Where to keep the manifest; by default `emojis.lock.json` in `folder`.
        prune: Delete emojis that have no image in the folder.
        replace_unknown: Replace emojis the manifest does not know instead of adopting them.
        dry_run: Only report what would change.
        rounds: How many times to try an emoji that fails for a temporary reason.
        clock: Waits between rounds.

    Raises:
        NotADirectoryError: `folder` is not a directory.
        ValueError: `rounds` is below 1.
    """
    if rounds < 1:
        msg = "a sync needs at least one round"
        raise ValueError(msg)
    manifest_path = manifest or folder / MANIFEST_NAME
    report = SyncReport(dry_run=dry_run)
    local, invalid = await asyncio.to_thread(find_emojis, folder)
    report.failed.update(invalid)
    stored = await asyncio.to_thread(read_manifest, manifest_path)
    known = stored.applications.setdefault(str(int(application_id)), {})
    remote = _named(await rest.emojis.list_for_application(application_id))
    plan = _plan(local, remote, known, report, prune=prune, replace_unknown=replace_unknown)
    if dry_run:
        report.created.extend(item.name for item in plan.create)
        report.replaced.extend(item.name for item, _ in plan.replace)
        report.deleted.extend(emoji.name for emoji in plan.delete)
        return report
    syncer = _Syncer(rest, application_id, known=known, manifest=stored, path=manifest_path, report=report)
    await syncer.save()
    for emoji in plan.delete:
        await syncer.delete(emoji)
    waiter = clock or SystemClock()
    pending: list[tuple[LocalEmoji, _Remote | None]] = [
        *((item, previous) for item, previous in plan.replace),
        *((item, None) for item in plan.create),
    ]
    for attempt in range(1, rounds + 1):
        retry: list[tuple[LocalEmoji, _Remote | None]] = []
        for item, previous in pending:
            if not await syncer.upload(item, previous, last_round=attempt == rounds):
                retry.append((item, previous))
        if not retry:
            break
        pending = retry
        _log.info("retrying %d emojis in %.0fs", len(retry), SYNC_ROUND_PAUSE * attempt)
        await waiter.sleep(SYNC_ROUND_PAUSE * attempt)
    return report


def _named(emojis: Iterable[Emoji]) -> dict[str, _Remote]:
    """The application's emojis by name; every application emoji has both."""
    return {
        emoji.name: _Remote(emoji.name, emoji.id)
        for emoji in emojis
        if emoji.name is not None and emoji.id is not None
    }


def _plan(
    local: dict[str, LocalEmoji],
    remote: dict[str, _Remote],
    known: dict[str, ManifestEntry],
    report: SyncReport,
    *,
    prune: bool,
    replace_unknown: bool,
) -> _Plan:
    """Sort every emoji into what to create, replace, delete, or leave, recording adoptions."""
    create: list[LocalEmoji] = []
    replace: list[tuple[LocalEmoji, _Remote]] = []
    for name, item in sorted(local.items()):
        existing = remote.get(name)
        entry = known.get(name)
        if existing is None:
            create.append(item)
        elif entry is None or entry.id != existing.id:
            if replace_unknown:
                replace.append((item, existing))
            else:
                known[name] = ManifestEntry(id=int(existing.id), sha256=item.sha256)
                report.adopted.append(name)
        elif entry.sha256 != item.sha256:
            replace.append((item, existing))
        else:
            report.unchanged.append(name)
    extra = [emoji for name, emoji in sorted(remote.items()) if name not in local]
    delete = extra if prune else []
    if not prune:
        report.unmanaged.extend(emoji.name for emoji in extra)
    room = APPLICATION_MAX_EMOJIS - (len(remote) - len(delete))
    for item in create[max(room, 0) :]:
        report.failed[item.name] = (
            f"the application already has {APPLICATION_MAX_EMOJIS} emojis, the most allowed"
        )
    return _Plan(create=create[: max(room, 0)], replace=replace, delete=delete)


class _Syncer:
    """Carries out a plan, saving the manifest after every change so an interrupted sync keeps them."""

    __slots__ = ("_application_id", "_known", "_manifest", "_path", "_removed", "_report", "_rest")

    def __init__(
        self,
        rest: RestClient,
        application_id: int,
        *,
        known: dict[str, ManifestEntry],
        manifest: Manifest,
        path: Path,
        report: SyncReport,
    ) -> None:
        self._rest: RestClient = rest
        self._application_id: int = application_id
        self._known: dict[str, ManifestEntry] = known
        self._removed: set[Snowflake] = set()
        """Emojis already deleted, so a replacement tried again does not delete its old one twice."""
        self._manifest: Manifest = manifest
        self._path: Path = path
        self._report: SyncReport = report

    async def save(self) -> None:
        data = msgspec.json.format(msgspec.json.encode(self._manifest), indent=2) + b"\n"
        await asyncio.to_thread(write_private, self._path, data)

    async def delete(self, emoji: _Remote) -> None:
        try:
            await self._remove(emoji.id)
        except (HTTPError, TransportError) as error:
            self._fail(emoji.name, error)
            return
        self._known.pop(emoji.name, None)
        self._report.deleted.append(emoji.name)
        await self.save()

    async def upload(self, item: LocalEmoji, previous: _Remote | None, *, last_round: bool) -> bool:
        """Create `item`, after deleting `previous`; `False` when it should be tried again."""
        try:
            if previous is not None and previous.id not in self._removed:
                await self._remove(previous.id)
                self._removed.add(previous.id)
                self._known.pop(item.name, None)
            created = await self._create(item)
        except (ServerError, TransportError) as error:
            if not last_round:
                _log.warning("emoji %r failed for now (%s); trying again later", item.name, error)
                return False
            self._fail(item.name, error)
            return True
        except HTTPError as error:
            self._fail(item.name, error)
            return True
        self._known[item.name] = ManifestEntry(id=int(created.id), sha256=item.sha256)
        (self._report.replaced if previous is not None else self._report.created).append(item.name)
        await self.save()
        return True

    async def _create(self, item: LocalEmoji) -> _Remote:
        params = CreateApplicationEmojiParams(
            name=item.name, image=emoji_data(await asyncio.to_thread(item.path.read_bytes))
        )
        try:
            created = await self._rest.emojis.create_for_application(self._application_id, params)
        except BadRequestError:
            # An earlier sync that was stopped mid-upload, or another process, may have created it
            # since the listing; that emoji is ours to replace.
            listed = await self._rest.emojis.list_for_application(self._application_id)
            taken = _named(listed).get(item.name)
            if taken is None:
                raise
            await self._remove(taken.id)
            created = await self._rest.emojis.create_for_application(self._application_id, params)
        [made] = _named([created]).values()
        return made

    async def _remove(self, emoji_id: Snowflake) -> None:
        await self._rest.emojis.delete_for_application(self._application_id, emoji_id)

    def _fail(self, name: str, error: Exception) -> None:
        _log.error("emoji %r could not be synced: %s", name, error)
        self._report.failed[name] = str(error)


def find_emojis(folder: Path) -> tuple[dict[str, LocalEmoji], dict[str, str]]:
    """The emoji images in `folder` by name, and the files that cannot be emojis, with the reason.

    Blocks; call it through `asyncio.to_thread`.

    Raises:
        NotADirectoryError: `folder` is not a directory.
    """
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    by_name: dict[str, list[Path]] = {}
    for path in sorted(_images(folder.rglob("*"))):
        by_name.setdefault(path.stem, []).append(path)
    found: dict[str, LocalEmoji] = {}
    invalid: dict[str, str] = {}
    for name, paths in by_name.items():
        if len(paths) > 1:
            listed = ", ".join(str(path.relative_to(folder)) for path in paths)
            invalid[name] = f"{len(paths)} images share the name: {listed}"
            continue
        [path] = paths
        data = path.read_bytes()
        if len(data) > EMOJI_MAX_SIZE:
            invalid[name] = (
                f"{path.name} is {len(data) // 1024} KiB; emojis are at most {EMOJI_MAX_SIZE // 1024} KiB"
            )
        elif emoji_content_type(data) is None:
            invalid[name] = f"{path.name} is not a JPEG, PNG, GIF, WebP or AVIF image"
        else:
            found[name] = LocalEmoji(name=name, path=path, sha256=hashlib.sha256(data).hexdigest())
    return found, invalid


def _images(paths: Iterable[Path]) -> Iterable[Path]:
    return (path for path in paths if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def read_manifest(path: Path) -> Manifest:
    """The manifest at `path`; an empty one when there is none yet.

    Blocks; call it through `asyncio.to_thread`.

    Raises:
        msgspec.DecodeError: The file is not a manifest.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return Manifest()
    return msgspec.json.decode(data, type=Manifest)
