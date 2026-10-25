"""Generate one API reference page per module, so the reference always matches the code.

Run by the mkdocs `gen-files` plugin at build time; nothing it writes is committed. The navigation is
written as a literate-nav `SUMMARY.md`: each package is a section whose first page is the package's
own overview, followed by its modules and subpackages.
"""

from dataclasses import dataclass, field
from pathlib import Path

import mkdocs_gen_files

SOURCE = Path(__file__).resolve().parent.parent / "src"


@dataclass
class Package:
    """One package in the navigation tree."""

    page: str | None = None
    modules: dict[str, str] = field(default_factory=dict[str, str])
    packages: dict[str, "Package"] = field(default_factory=dict[str, "Package"])


def package_at(tree: Package, parts: tuple[str, ...]) -> Package:
    """The package node for `parts`, creating any that are missing."""
    node = tree
    for part in parts:
        node = node.packages.setdefault(part, Package())
    return node


def summary(node: Package, title: str, depth: int) -> list[str]:
    """Literate-nav lines for `node`: an overview page first, then modules, then subpackages."""
    indent = "    " * depth
    lines = [f"{indent}* {title}\n"]
    if node.page is not None:
        lines.append(f"{indent}    * [Overview]({node.page})\n")
    lines.extend(f"{indent}    * [{name}]({page})\n" for name, page in sorted(node.modules.items()))
    for name, child in sorted(node.packages.items()):
        lines.extend(summary(child, name, depth + 1))
    return lines


tree = Package()
for path in sorted((SOURCE / "shoal").rglob("*.py")):
    module = path.relative_to(SOURCE).with_suffix("")
    parts = tuple(module.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
        page = Path("reference", *parts, "index.md")
        package_at(tree, parts).page = page.relative_to("reference").as_posix()
    elif parts[-1].startswith("_"):
        continue
    else:
        page = Path("reference", *parts).with_suffix(".md")
        package_at(tree, parts[:-1]).modules[parts[-1]] = page.relative_to("reference").as_posix()
    with mkdocs_gen_files.open(page, "w") as handle:
        handle.write(f"::: {'.'.join(parts)}\n")
    mkdocs_gen_files.set_edit_path(page, Path("..", path.relative_to(SOURCE.parent)))

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as handle:
    handle.writelines(summary(tree.packages["shoal"], "shoal", 0))
