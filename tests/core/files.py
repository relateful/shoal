import stat
import sys
from pathlib import Path

import pytest

from shoal.core.files import write_private
from tests.support.calls import call_unchecked


def test_write_private_replaces_the_file_and_leaves_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.bin"
    write_private(target, b"first")
    write_private(target, b"second")
    assert target.read_bytes() == b"second"
    assert [path.name for path in target.parent.iterdir()] == ["state.bin"]


def test_write_private_keeps_the_old_file_when_the_write_fails(tmp_path: Path) -> None:
    target = tmp_path / "state.bin"
    write_private(target, b"old")
    with pytest.raises(TypeError):
        call_unchecked(write_private, target, "not bytes")
    assert target.read_bytes() == b"old"
    assert [path.name for path in tmp_path.iterdir()] == ["state.bin"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_write_private_is_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "private" / "state.bin"
    write_private(target, b"x")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
