import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
generate_exports = importlib.import_module("generate_exports")


def test_public_names_cover_every_kind_of_definition(tmp_path: Path) -> None:
    module = tmp_path / "sample.py"
    module.write_text(
        "from typing import Final\n"
        "LIMIT: Final = 1\n"
        "_PRIVATE: Final = 2\n"
        "plain = 3\n"
        "type Alias = int | str\n"
        "type _Hidden = int\n"
        "class Thing: ...\n"
        "class _Helper: ...\n"
        "def build() -> None: ...\n"
        "def _internal() -> None: ...\n",
        encoding="utf-8",
    )
    assert generate_exports.public_names(module) == ["LIMIT", "Alias", "Thing", "build"]
