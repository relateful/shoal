"""Sort each module's block of public `Final` constants alphabetically.

A "block" is a run of top-level `NAME: Final = ...` statements, each optionally followed by its
docstring, with nothing else between them. Blocks are sorted in place; everything else is untouched.
An `ALL_*` aggregate (a tuple of the constants above it) is not sorted: it must come last in its
block, since it refers to every other constant there.
`tests/conventions.py` fails when a block is out of order; run this to fix it.

    uv run python scripts/sort_constants.py
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src" / "shoal"


@dataclass(frozen=True, slots=True)
class Constant:
    """One constant and the lines it spans, including its docstring."""

    name: str
    start: int
    end: int


def _is_public_final(node: ast.stmt) -> str | None:
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and not node.target.id.startswith("_")
        and not node.target.id.startswith("ALL_")
        and "Final" in ast.unparse(node.annotation)
    ):
        return node.target.id
    return None


def constant_blocks(tree: ast.Module) -> list[list[Constant]]:
    """Runs of consecutive public constants (each with its optional docstring)."""
    blocks: list[list[Constant]] = []
    current: list[Constant] = []
    body = tree.body
    index = 0
    while index < len(body):
        node = body[index]
        name = _is_public_final(node)
        if name is None:
            if current:
                blocks.append(current)
                current = []
            index += 1
            continue
        end = node.end_lineno or node.lineno
        following = body[index + 1] if index + 1 < len(body) else None
        if (
            isinstance(following, ast.Expr)
            and isinstance(following.value, ast.Constant)
            and isinstance(following.value.value, str)
        ):
            end = following.end_lineno or following.lineno
            index += 1
        current.append(Constant(name, node.lineno, end))
        index += 1
    if current:
        blocks.append(current)
    return blocks


def unsorted_blocks(path: Path) -> list[list[str]]:
    """The names in each out-of-order block of `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        [constant.name for constant in block]
        for block in constant_blocks(tree)
        if [constant.name for constant in block] != sorted(constant.name for constant in block)
    ]


def sort_file(path: Path) -> bool:
    """Sort every constant block of `path` in place. Returns whether anything moved."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = False
    for block in reversed(constant_blocks(ast.parse(text))):
        names = [constant.name for constant in block]
        if names == sorted(names):
            continue
        chunks = {
            constant.name: "".join(lines[constant.start - 1 : constant.end]).rstrip("\n")
            for constant in block
        }
        rebuilt = "\n\n".join(chunks[name] for name in sorted(names)) + "\n"
        lines[block[0].start - 1 : block[-1].end] = [rebuilt]
        changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8", newline="\n")
    return changed


def main() -> int:
    """Sort every module, or with `--check` only report unsorted blocks."""
    check = "--check" in sys.argv
    failed = False
    for path in sorted(SOURCE.rglob("*.py")):
        if check:
            for names in unsorted_blocks(path):
                print(f"{path.relative_to(SOURCE.parent)}: constants out of order: {', '.join(names)}")
                failed = True
        elif sort_file(path):
            print(f"sorted {path.relative_to(SOURCE.parent)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
