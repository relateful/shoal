import logging
from pathlib import Path

import msgspec
import pytest

from shoal.emojis.sync import Manifest, ManifestEntry, SyncReport, read_manifest, sync_emojis
from shoal.payloads import APPLICATION_MAX_EMOJIS
from shoal.rest.client import RestClient
from tests.support.fakes import FakeClock, FakeTransport
from tests.support.rest import make_client

APP = 7
PNG = b"\x89PNG\r\n\x1a\n"

type Json = dict[str, object]


def image(folder: Path, name: str, content: bytes = b"one") -> Path:
    path = folder / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG + content)
    return path


def remote(emoji_id: int, name: str) -> Json:
    return {"id": str(emoji_id), "name": name, "animated": False}


def listing(*emojis: Json) -> Json:
    return {"items": list(emojis)}


def requests(transport: FakeTransport) -> list[str]:
    """Each request as `METHOD /path`, without the API prefix."""
    return [f"{request.method} {request.url.split('/v10', 1)[1]}" for request in transport.requests]


def manifest(folder: Path) -> dict[str, ManifestEntry]:
    return read_manifest(folder / "emojis.lock.json").applications.get(str(APP), {})


async def run(
    rest: RestClient,
    folder: Path,
    *,
    prune: bool = False,
    replace_unknown: bool = False,
    dry_run: bool = False,
) -> SyncReport:
    return await sync_emojis(
        rest, APP, folder, prune=prune, replace_unknown=replace_unknown, dry_run=dry_run, clock=FakeClock()
    )


async def test_missing_emojis_are_created_and_recorded(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    image(tmp_path / "nested", "deny")
    transport = FakeTransport()
    transport.queue(200, listing())
    transport.queue(200, remote(101, "approve"))
    transport.queue(200, remote(102, "deny"))
    report = await run(make_client(transport), tmp_path)
    assert report.created == ["approve", "deny"]
    assert report.ok
    assert str(report) == "synced: 2 created"
    assert [entry.id for entry in manifest(tmp_path).values()] == [101, 102]
    body = msgspec.json.decode(transport.requests[1].body or b"")
    assert body["name"] == "approve"
    assert body["image"].startswith("data:image/png;base64,")


async def test_a_second_sync_uploads_nothing(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    first = FakeTransport()
    first.queue(200, listing())
    first.queue(200, remote(101, "approve"))
    await run(make_client(first), tmp_path)
    second = FakeTransport()
    second.queue(200, listing(remote(101, "approve")))
    report = await run(make_client(second), tmp_path)
    assert report.unchanged == ["approve"]
    assert requests(second) == [f"GET /applications/{APP}/emojis"]


async def test_a_changed_image_replaces_its_emoji(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    first = FakeTransport()
    first.queue(200, listing())
    first.queue(200, remote(101, "approve"))
    await run(make_client(first), tmp_path)
    image(tmp_path, "approve", b"two")
    second = FakeTransport()
    second.queue(200, listing(remote(101, "approve")))
    second.queue(204)
    second.queue(200, remote(202, "approve"))
    report = await run(make_client(second), tmp_path)
    assert report.replaced == ["approve"]
    assert requests(second)[1:] == [
        f"DELETE /applications/{APP}/emojis/101",
        f"POST /applications/{APP}/emojis",
    ]
    assert manifest(tmp_path)["approve"].id == 202


async def test_emojis_the_manifest_does_not_know_are_adopted(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    transport = FakeTransport()
    transport.queue(200, listing(remote(101, "approve")))
    report = await run(make_client(transport), tmp_path)
    assert report.adopted == ["approve"]
    assert len(transport.requests) == 1
    assert manifest(tmp_path)["approve"].id == 101


async def test_unknown_emojis_can_be_replaced_instead(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    transport = FakeTransport()
    transport.queue(200, listing(remote(101, "approve")))
    transport.queue(204)
    transport.queue(200, remote(202, "approve"))
    report = await run(make_client(transport), tmp_path, replace_unknown=True)
    assert report.replaced == ["approve"]


async def test_emojis_without_an_image_are_left_alone_unless_pruned(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    kept = FakeTransport()
    kept.queue(200, listing(remote(101, "approve"), remote(103, "old")))
    report = await run(make_client(kept), tmp_path)
    assert report.unmanaged == ["old"]
    assert str(report) == "synced: 1 adopted, 1 left alone"
    pruned = FakeTransport()
    pruned.queue(200, listing(remote(101, "approve"), remote(103, "old")))
    pruned.queue(204)
    report = await run(make_client(pruned), tmp_path, prune=True)
    assert report.deleted == ["old"]
    assert requests(pruned)[-1] == f"DELETE /applications/{APP}/emojis/103"


async def test_a_dry_run_changes_nothing(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    image(tmp_path, "deny")
    transport = FakeTransport()
    transport.queue(200, listing(remote(103, "old")))
    report = await run(make_client(transport), tmp_path, dry_run=True, prune=True)
    assert report.created == ["approve", "deny"]
    assert report.deleted == ["old"]
    assert str(report) == "would sync (dry run): 2 created, 1 deleted"
    assert len(transport.requests) == 1
    assert not (tmp_path / "emojis.lock.json").exists()


async def test_files_that_cannot_be_emojis_are_reported(tmp_path: Path) -> None:
    image(tmp_path, "twice")
    image(tmp_path / "other", "twice")
    (tmp_path / "large.png").write_bytes(PNG + b"\x00" * (256 * 1024))
    (tmp_path / "bitmap.png").write_bytes(b"BM not an emoji format")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    transport = FakeTransport()
    transport.queue(200, listing())
    report = await run(make_client(transport), tmp_path)
    assert sorted(report.failed) == ["bitmap", "large", "twice"]
    assert "2 images share the name" in report.failed["twice"]
    assert "256 KiB" in report.failed["large"]
    assert not report.ok
    assert "failed bitmap: bitmap.png is not a JPEG, PNG, GIF, WebP or AVIF image" in str(report)


async def test_temporary_failures_are_tried_again(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    transport = FakeTransport()
    transport.queue(200, listing())
    transport.queue(502, {"message": "Bad Gateway", "code": 0})
    transport.queue(200, remote(101, "approve"))
    clock = FakeClock()
    report = await sync_emojis(make_client(transport), APP, tmp_path, clock=clock)
    assert report.created == ["approve"]
    assert clock.sleeps == [5.0]


async def test_failures_that_last_are_reported(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    image(tmp_path, "approve")
    transport = FakeTransport()
    transport.queue(200, listing())
    for _ in range(2):
        transport.queue(503, {"message": "Unavailable", "code": 0})
    with caplog.at_level(logging.ERROR, logger="shoal.emojis"):
        report = await sync_emojis(make_client(transport), APP, tmp_path, rounds=2, clock=FakeClock())
    assert list(report.failed) == ["approve"]
    assert "could not be synced" in caplog.text


async def test_a_name_left_by_an_interrupted_sync_is_replaced(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    transport = FakeTransport()
    transport.queue(200, listing())
    transport.queue(400, {"message": "Invalid Form Body", "code": 50035})
    transport.queue(200, listing(remote(99, "approve")))
    transport.queue(204)
    transport.queue(200, remote(101, "approve"))
    report = await run(make_client(transport), tmp_path)
    assert report.created == ["approve"]
    assert f"DELETE /applications/{APP}/emojis/99" in requests(transport)


async def test_a_rejected_upload_is_reported_without_retrying(tmp_path: Path) -> None:
    image(tmp_path, "approve")
    transport = FakeTransport()
    transport.queue(200, listing())
    transport.queue(400, {"message": "Invalid Form Body", "code": 50035})
    transport.queue(200, listing())
    report = await run(make_client(transport), tmp_path)
    assert "Invalid Form Body" in report.failed["approve"]
    assert len(transport.requests) == 3


async def test_a_failed_prune_is_reported(tmp_path: Path) -> None:
    transport = FakeTransport()
    transport.queue(200, listing(remote(103, "old")))
    transport.queue(403, {"message": "Missing Access", "code": 50001})
    report = await run(make_client(transport), tmp_path, prune=True)
    assert "Missing Access" in report.failed["old"]


async def test_the_application_limit_is_kept(tmp_path: Path) -> None:
    image(tmp_path, "extra")
    existing = [remote(index + 1, f"e{index}") for index in range(APPLICATION_MAX_EMOJIS)]
    transport = FakeTransport()
    transport.queue(200, listing(*existing))
    report = await run(make_client(transport), tmp_path)
    assert "2000 emojis" in report.failed["extra"]
    assert len(report.unmanaged) == APPLICATION_MAX_EMOJIS


async def test_each_application_keeps_its_own_entries(tmp_path: Path) -> None:
    path = tmp_path / "emojis.lock.json"
    other = Manifest(applications={"8": {"approve": ManifestEntry(id=5, sha256="x")}})
    path.write_bytes(msgspec.json.encode(other))
    image(tmp_path, "approve")
    transport = FakeTransport()
    transport.queue(200, listing())
    transport.queue(200, remote(101, "approve"))
    await run(make_client(transport), tmp_path)
    stored = read_manifest(path)
    assert stored.applications["8"]["approve"].id == 5
    assert stored.applications[str(APP)]["approve"].id == 101


async def test_a_sync_needs_a_folder_and_a_round(tmp_path: Path) -> None:
    rest = make_client(FakeTransport())
    with pytest.raises(ValueError, match="at least one round"):
        await sync_emojis(rest, APP, tmp_path, rounds=0)
    with pytest.raises(NotADirectoryError):
        await sync_emojis(rest, APP, tmp_path / "missing")
