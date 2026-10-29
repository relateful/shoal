"""Print the CHANGELOG.md section for a version, for its GitHub release notes.

Fails when the changelog has no `## [<version>]` section or the section is empty, so a release
cannot be tagged before its entries are moved out of "Unreleased".

    uv run python scripts/release_notes.py 0.1.0
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(changelog: str, version: str) -> str | None:
    """The body of `## [version]`, up to the next `## ` heading, or `None` if missing or empty."""
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)", changelog, re.MULTILINE | re.DOTALL
    )
    if match is None:
        return None
    body = match.group(1).strip()
    return body or None


def main() -> int:
    """Print the section for the version in `sys.argv[1]`."""
    if len(sys.argv) != 2:  # noqa: PLR2004 - the script name and the version
        print("usage: release_notes.py <version>", file=sys.stderr)
        return 2
    version = sys.argv[1]
    body = section(CHANGELOG.read_text(encoding="utf-8"), version)
    if body is None:
        print(f"CHANGELOG.md has no entries under '## [{version}]'", file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
