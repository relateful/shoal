"""Generate one API reference page per module, so the reference always matches the code.

Run by the mkdocs `gen-files` plugin at build time; nothing it writes is committed.
"""

from pathlib import Path

import mkdocs_gen_files

SOURCE = Path(__file__).resolve().parent.parent / "src"

navigation = mkdocs_gen_files.Nav()
for path in sorted((SOURCE / "shoal").rglob("*.py")):
    module = path.relative_to(SOURCE).with_suffix("")
    parts = tuple(module.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
        page = Path("reference", *parts, "index.md")
    elif parts[-1].startswith("_"):
        continue
    else:
        page = Path("reference", *parts).with_suffix(".md")
    navigation[parts] = page.relative_to("reference").as_posix()
    with mkdocs_gen_files.open(page, "w") as handle:
        handle.write(f"::: {'.'.join(parts)}\n")
    mkdocs_gen_files.set_edit_path(page, Path("..", path.relative_to(SOURCE.parent)))

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as handle:
    handle.writelines(navigation.build_literate_nav())
