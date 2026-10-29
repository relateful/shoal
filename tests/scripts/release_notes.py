import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
release_notes = importlib.import_module("release_notes")

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Something new.

## [0.2.0] - 2026-11-01

### Fixed

- A fix.

## [0.1.0] - 2026-10-30

## [0.0.1] - 2026-10-01

- First.
"""


def test_a_version_section_is_its_body_up_to_the_next_heading() -> None:
    assert release_notes.section(CHANGELOG, "0.2.0") == "### Fixed\n\n- A fix."
    assert release_notes.section(CHANGELOG, "0.0.1") == "- First."


def test_a_missing_or_empty_section_is_none() -> None:
    assert release_notes.section(CHANGELOG, "9.9.9") is None
    assert release_notes.section(CHANGELOG, "0.1.0") is None
    # A dot in the version is not a wildcard.
    assert release_notes.section(CHANGELOG, "0x2x0") is None


def test_main_prints_the_section_or_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(release_notes, "CHANGELOG", changelog)
    monkeypatch.setattr(sys, "argv", ["release_notes.py", "0.2.0"])
    assert release_notes.main() == 0
    assert capsys.readouterr().out == "### Fixed\n\n- A fix.\n"
    monkeypatch.setattr(sys, "argv", ["release_notes.py", "9.9.9"])
    assert release_notes.main() == 1
    monkeypatch.setattr(sys, "argv", ["release_notes.py"])
    assert release_notes.main() == 2
