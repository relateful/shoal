"""Project rules, enforced.

Each test here is one rule from CONTRIBUTING.md that a linter or type checker cannot express. They
run over the whole tree, so a rule cannot hold in one area and quietly lapse in another.
"""

import ast
import dataclasses
import importlib
import importlib.util
import inspect
import re
import subprocess
import sys
import typing
from collections import Counter
from enum import Enum
from pathlib import Path

import msgspec
import pytest

import shoal.payloads
from shoal.core.codec import json_decoder, msgpack_decoder
from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
from shoal.core.errors import ShoalError
from shoal.core.flags import BaseFlags
from shoal.core.metrics import ALL_METRICS
from shoal.payloads.base import Payload
from tests.support.rest import endpoint_methods

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "shoal"
TESTS = ROOT / "tests"
SCRIPTS = ROOT / "scripts"
DOCS_LINK = re.compile(r"https://docs\.discord\.com/developers/[a-z0-9/-]*(?:#[a-z0-9/_.-]+)?")
ANY_DISCORD_DOCS_URL = re.compile(r"https?://(?:docs\.)?discord(?:app)?\.com/(?:developers|docs)[^\s)\"'`>]*")

sys.path.insert(0, str(SCRIPTS))
generate_exports = importlib.import_module("generate_exports")
sort_constants = importlib.import_module("sort_constants")


def source_modules() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE.parent).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(parts)


def has_behaviour(tree: ast.Module) -> bool:
    """Whether a module defines a function, or a class with at least one method."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            return True
        if isinstance(node, ast.ClassDef) and any(
            isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef) for member in node.body
        ):
            return True
    return False


def public_payload_types() -> list[type]:
    exported = (getattr(shoal.payloads, name) for name in shoal.payloads.__all__)
    return [value for value in exported if inspect.isclass(value) and value is not Payload]


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_every_module_has_a_docstring(path: Path) -> None:
    assert ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))), f"{path} has no module docstring"


@pytest.mark.parametrize(
    "path",
    [path for path in source_modules() if path.name != "__init__.py"],
    ids=module_name,
)
def test_every_module_with_behaviour_has_a_mirrored_test_module(path: Path) -> None:
    if not has_behaviour(ast.parse(path.read_text(encoding="utf-8"))):
        return
    mirror = TESTS / path.relative_to(SOURCE)
    assert mirror.exists(), (
        f"{module_name(path)} has behaviour but no test module at {mirror.relative_to(ROOT)}"
    )


def test_test_modules_are_named_after_what_they_test() -> None:
    prefixed = [path.relative_to(ROOT) for path in TESTS.rglob("test_*.py")]
    assert prefixed == [], "test modules mirror source names; the tests/ folder already says they are tests"


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_discord_links_use_the_canonical_docs_site(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for url in ANY_DISCORD_DOCS_URL.findall(text):
        assert DOCS_LINK.fullmatch(url.rstrip(".,")), f"{module_name(path)}: non-canonical docs link {url}"


BANNER_COMMENT = re.compile(r"^\s*#.*-{4,}\s*$", re.MULTILINE)
OTHER_LIBRARY = re.compile(r"discord\.py|\bdpy\b", re.IGNORECASE)


def python_files() -> list[Path]:
    return sorted(path for folder in (SOURCE, TESTS, SCRIPTS) for path in folder.rglob("*.py"))


@pytest.mark.parametrize("path", python_files(), ids=lambda path: str(path.relative_to(ROOT)))
def test_code_has_no_banner_comments_or_other_library_names(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    banners = [match.group().strip() for match in BANNER_COMMENT.finditer(text)]
    assert banners == [], "split a module rather than marking sections with banner comments"
    others = [line.strip() for line in text.splitlines() if OTHER_LIBRARY.search(line)]
    assert others == [], "code describes Shoal on its own terms; only comparison docs name other libraries"


@pytest.mark.parametrize("payload_type", public_payload_types(), ids=lambda value: value.__name__)
def test_every_payload_type_links_to_its_discord_docs(payload_type: type) -> None:
    docstring = inspect.getdoc(payload_type) or ""
    assert "Discord: https://docs.discord.com/developers/" in docstring, (
        f"{payload_type.__name__} has no docs link"
    )


@pytest.mark.parametrize(
    "payload_type",
    [value for value in public_payload_types() if issubclass(value, Payload)],
    ids=lambda value: value.__name__,
)
def test_every_payload_type_can_be_decoded(payload_type: type[Payload]) -> None:
    json_decoder(payload_type)
    msgpack_decoder(payload_type)


@pytest.mark.parametrize(
    "enum_type",
    [value for value in public_payload_types() if issubclass(value, Enum)],
    ids=lambda value: value.__name__,
)
def test_discord_enums_are_ordered(enum_type: type[Enum]) -> None:
    values = [member.value for member in enum_type]
    assert issubclass(enum_type, DiscordIntEnum | DiscordStrEnum), (
        f"{enum_type.__name__} must be an open enum"
    )
    assert values == sorted(values), f"{enum_type.__name__}: members must be in value order"


@pytest.mark.parametrize(
    "flags_type",
    [value for value in public_payload_types() if issubclass(value, BaseFlags)],
    ids=lambda value: value.__name__,
)
def test_flags_are_declared_in_bit_order_with_slots(flags_type: type[BaseFlags]) -> None:
    bits = list(flags_type.known_flags.values())
    assert bits == sorted(bits), f"{flags_type.__name__}: flags must be declared in bit order"
    assert vars(flags_type).get("__slots__") == (), f"{flags_type.__name__} must declare __slots__ = ()"


def test_constant_blocks_are_alphabetical() -> None:
    problems = [
        f"{path.relative_to(ROOT)}: {', '.join(names)}"
        for path in source_modules()
        for names in sort_constants.unsorted_blocks(path)
    ]
    assert problems == [], "run scripts/sort_constants.py"


def test_constants_are_defined_once() -> None:
    names: Counter[str] = Counter()
    for path in source_modules():
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                if name.isupper() and not name.startswith("_") and "Final" in ast.unparse(node.annotation):
                    names[name] += 1
    duplicated = sorted(name for name, count in names.items() if count > 1)
    assert duplicated == [], f"constants defined in more than one module: {duplicated}"


def test_payload_exports_are_generated() -> None:
    expected = generate_exports.render()
    assert (SOURCE / "payloads" / "__init__.py").read_text(encoding="utf-8") == expected, (
        "run scripts/generate_exports.py"
    )


@pytest.mark.parametrize(
    "path",
    [path for path in source_modules() if path.name == "__init__.py"],
    ids=module_name,
)
def test_package_exports_exist(path: Path) -> None:
    """Every package declares `__all__` and every listed name exists. Ruff (RUF022) keeps it sorted."""
    module = importlib.import_module(module_name(path))
    exported: object = getattr(module, "__all__", None)
    assert exported is not None, f"{module_name(path)} must declare __all__"
    for name in msgspec.convert(exported, list[str]):
        assert hasattr(module, name), f"{module_name(path)}.__all__ lists missing {name}"


def classes_defined_in(path: Path) -> list[type[object]]:
    module = importlib.import_module(module_name(path))
    return [
        value
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__
    ]


def needs_slots(cls: type[object]) -> bool:
    """Plain classes that hold state; structs, enums, exceptions, protocols, TypedDicts manage their own."""
    if issubclass(cls, msgspec.Struct | Enum | BaseException | type) or getattr(cls, "_is_protocol", False):
        return False
    if typing.is_typeddict(cls):
        return False
    return not dataclasses.is_dataclass(cls)


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_classes_with_state_declare_slots(path: Path) -> None:
    for cls in classes_defined_in(path):
        if dataclasses.is_dataclass(cls):
            assert "__slots__" in vars(cls), f"{cls.__qualname__}: dataclasses must use slots=True"
        elif needs_slots(cls):
            assert "__slots__" in vars(cls), f"{cls.__qualname__} must declare __slots__"
        elif getattr(cls, "_is_protocol", False) and not typing.is_typeddict(cls):
            # A protocol without them gives every class built on it a __dict__, undoing their slots.
            assert vars(cls).get("__slots__") == (), f"{cls.__qualname__} must declare __slots__ = ()"


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_slots_leave_no_undeclared_instance_dict(path: Path) -> None:
    for cls in classes_defined_in(path):
        if "__slots__" not in vars(cls) or issubclass(cls, msgspec.Struct):
            continue
        declared = any("__dict__" in vars(base).get("__slots__", ()) for base in cls.__mro__)
        assert declared or cls.__dictoffset__ == 0, (
            f"{cls.__qualname__}: a base without __slots__ gives instances a __dict__"
        )


def test_every_rest_endpoint_method_links_to_its_docs() -> None:
    methods = endpoint_methods()
    assert methods
    for name, method in methods:
        assert "Discord: https://docs.discord.com/developers/" in (method.__doc__ or ""), name


def test_dispatch_tables_are_alphabetical() -> None:
    for path in source_modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Dict)
                and node.keys
                and all(
                    isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value.isupper()
                    for key in node.keys
                )
            ):
                keys = [
                    key.value
                    for key in node.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                ]
                assert keys == sorted(keys), f"{module_name(path)}: table keys out of order {keys}"


@pytest.mark.parametrize("name", [spec.name for spec in ALL_METRICS])
def test_every_metric_is_documented(name: str) -> None:
    guide = (ROOT / "docs" / "guide" / "metrics.md").read_text(encoding="utf-8")
    assert f"| `{name}` |" in guide, f"{name} is missing from the table in docs/guide/metrics.md"


def test_text_files_hold_no_control_characters() -> None:
    files = [
        *SOURCE.rglob("*.py"),
        *TESTS.rglob("*.py"),
        *SCRIPTS.rglob("*.py"),
        *(ROOT / "docs").rglob("*.md"),
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
    ]
    corrupted = [
        str(path.relative_to(ROOT))
        for path in files
        if any(ord(char) < 0x20 and char not in "\n\r\t" for char in path.read_text(encoding="utf-8"))
    ]
    assert corrupted == [], "a scripted edit left control characters behind"


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_exceptions_derive_from_shoal_error(path: Path) -> None:
    for cls in classes_defined_in(path):
        if issubclass(cls, BaseException):
            assert issubclass(cls, ShoalError), f"{cls.__qualname__} must derive from ShoalError"
            assert cls.__name__.endswith("Error"), f"{cls.__qualname__}: exception names end in Error"


TIMING_CALLS = frozenset({
    "asyncio.sleep", "asyncio.wait_for", "asyncio.timeout", "time.monotonic", "time.time",
    "time.perf_counter", "datetime.now", "datetime.utcnow", "call_later", "call_at",
})  # fmt: skip
"""Calls that wait or tell the time without the injected `Clock`."""
CLOCK_MODULES = frozenset({"shoal.core.clock", "shoal.diagnostics.loop"})
"""The clock itself, and `LoopMonitor`, whose job is to measure the real event loop."""
SOCKET_TIMEOUT_MODULES = frozenset({"shoal.gateway.connection", "shoal.ipc.client", "shoal.ipc.server"})
"""Network adapters, whose connect and handshake timeouts wait on real sockets."""


def _called_name(node: ast.Call) -> str | None:
    function = node.func
    if isinstance(function, ast.Attribute):
        # Whatever the loop is called, scheduling on it bypasses the clock.
        if function.attr in {"call_later", "call_at"}:
            return function.attr
        if isinstance(function.value, ast.Name):
            return f"{function.value.id}.{function.attr}"
        return function.attr
    return None


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_delays_and_time_go_through_the_clock(path: Path) -> None:
    module = module_name(path)
    if module in CLOCK_MODULES:
        return
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        name = _called_name(node)
        if name not in TIMING_CALLS:
            continue
        # A zero sleep only yields to the loop.
        if name == "asyncio.sleep" and [ast.dump(arg) for arg in node.args] == [ast.dump(ast.Constant(0))]:
            continue
        if name in {"asyncio.wait_for", "asyncio.timeout"} and module in SOCKET_TIMEOUT_MODULES:
            continue
        found.append(f"line {node.lineno}: {name}")
    assert found == [], "take a Clock (core.clock: sleep, within) instead"


@pytest.mark.parametrize("path", [*source_modules(), *sorted(TESTS.rglob("*.py"))], ids=str)
def test_every_cast_says_why(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    unexplained: list[int] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "cast":
            end = node.end_lineno or node.lineno
            # The reason sits on the cast's own lines (formatting may move it to the last) or just above.
            span = lines[node.lineno - 2 : end]
            if not any("#" in line for line in span):
                unexplained.append(node.lineno)
    assert unexplained == [], "a cast names why the checker needs it, on its line or the line above"


def test_top_level_names_load_on_first_use() -> None:
    for name in shoal.__all__:
        assert getattr(shoal, name) is not None, name
    with pytest.raises(AttributeError, match="no attribute 'nothing'"):
        _ = shoal.nothing


def test_importing_one_layer_does_not_load_the_others() -> None:
    probe = (
        "import sys, shoal.core, shoal.payloads; "
        "print(sorted({'aiohttp', 'shoal.client'} & set(sys.modules)))"
    )
    # A fresh interpreter: this one has loaded everything already. The command is fixed above.
    loaded = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert loaded.stdout.strip() == "[]"


def test_every_package_is_named_wherever_the_layers_are_listed() -> None:
    packages = sorted(path.name for path in SOURCE.iterdir() if (path / "__init__.py").exists())
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "guide" / "architecture.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    overview = shoal.__doc__ or ""
    missing = [
        f"{package}: {where}"
        for package in packages
        for where, found in (
            ("CONTRIBUTING.md layout", f"  {package}/" in contributing),
            ("docs/guide/architecture.md table", f"| `{package}` |" in architecture),
            ("the shoal package docstring", f"`shoal.{package}`" in overview),
            ("the import-linter layers", f"shoal.{package}" in pyproject),
        )
        if not found
    ]
    assert missing == []


DOCS_IMPORT = re.compile(r"^\s*from (shoal[\w.]*) import ([\w, ]+)$", re.MULTILINE)


def _resolves(module_path: str, name: str) -> bool:
    """Whether `from module_path import name` works: an attribute, or a submodule."""
    if hasattr(importlib.import_module(module_path), name):
        return True
    return importlib.util.find_spec(f"{module_path}.{name}") is not None


def test_imports_in_the_docs_resolve() -> None:
    pages = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    broken = [
        f"{page.relative_to(ROOT)}: from {module_path} import {name}"
        for page in pages
        for module_path, names in DOCS_IMPORT.findall(page.read_text(encoding="utf-8"))
        for name in (part.strip() for part in names.split(","))
        if name and not _resolves(module_path, name)
    ]
    assert broken == []


BLOCKING_CALLS = frozenset({"read_bytes", "write_bytes", "read_text", "write_text", "open", "fdopen"})
"""File calls that block the event loop."""
BLOCKS_NOTE = "Blocks; call it through `asyncio.to_thread`."


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_blocking_file_calls_live_in_functions_that_say_so(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    unmarked: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKING_CALLS)
                or (isinstance(node.func, ast.Name) and node.func.id == "open")
            )
        ]
        if not calls:
            continue
        documented = BLOCKS_NOTE in (ast.get_docstring(function) or "")
        if isinstance(function, ast.AsyncFunctionDef) or not documented:
            unmarked.append(f"{function.name} (line {function.lineno})")
    assert unmarked == [], f"file I/O belongs in a sync function documented {BLOCKS_NOTE!r}"


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_queues_are_bounded(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    unbounded = [
        node.lineno
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Call)
        and _called_name(node) in {"deque", "asyncio.Queue", "Queue"}
        and not node.args
        and not node.keywords
        and "bounded" not in lines[node.lineno - 1]
    ]
    assert unbounded == [], "a queue takes a size, or says on its line what bounds it"


SECRET_FIELD = re.compile(r"(?:^|_)(?:token|secret|password|email)$")
"""Struct fields whose value must never appear in a repr: credentials and email addresses."""


def secret_fields_shown_in_reprs() -> list[str]:
    shown: list[str] = []
    for path in source_modules():
        module = importlib.import_module(module_name(path))
        for value in vars(module).values():
            if not (
                inspect.isclass(value)
                and issubclass(value, msgspec.Struct)
                and value.__module__ == module.__name__
            ):
                continue
            secrets = [name for name in value.__struct_fields__ if SECRET_FIELD.search(name)]
            if not secrets:
                continue
            if issubclass(value, Payload):
                shown.extend(
                    f"{value.__qualname__}.{name}" for name in secrets if name not in value.REDACTED_FIELDS
                )
            elif "__repr__" not in vars(value):
                shown.extend(f"{value.__qualname__}.{name}" for name in secrets)
    return shown


def test_credentials_and_emails_are_hidden_from_reprs() -> None:
    # A payload lists such fields in `REDACTED_FIELDS`; any other struct writes its own `__repr__`.
    assert secret_fields_shown_in_reprs() == []
