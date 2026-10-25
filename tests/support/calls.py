"""Calling something with arguments its signature forbids, to test the runtime check behind it."""

from collections.abc import Callable


def call_unchecked(target: Callable[..., object], *arguments: object) -> object:
    """Call `target` positionally with `arguments`, hidden from the type checker on purpose.

    Tests use this to prove that a call the type checker would reject also fails at runtime, without a
    `type: ignore` that would have to name a different error code for every checker.
    """
    return target(*arguments)
