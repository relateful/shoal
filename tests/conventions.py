"""Project rules, enforced.

Each test here is one rule from CONTRIBUTING.md that a linter or type checker cannot express. They
run over the whole tree, so a rule cannot hold in one area and quietly lapse in another.
"""

import ast
import dataclasses
import importlib
import inspect
import re
import sys
from collections import Counter
from enum import Enum
from pathlib import Path

import msgspec
import pytest

import shoal.payloads
from shoal.core.codec import json_decoder, msgpack_decoder
from shoal.core.enums import DiscordIntEnum, DiscordStrEnum
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
    """Plain classes that hold state; msgspec structs, enums, exceptions and protocols manage their own."""
    if issubclass(cls, msgspec.Struct | Enum | BaseException | type) or getattr(cls, "_is_protocol", False):
        return False
    return not dataclasses.is_dataclass(cls)


@pytest.mark.parametrize("path", source_modules(), ids=module_name)
def test_classes_with_state_declare_slots(path: Path) -> None:
    for cls in classes_defined_in(path):
        if dataclasses.is_dataclass(cls):
            assert "__slots__" in vars(cls), f"{cls.__qualname__}: dataclasses must use slots=True"
        elif needs_slots(cls):
            assert "__slots__" in vars(cls), f"{cls.__qualname__} must declare __slots__"


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
