"""The base class for every payload type.

How Discord's field notation maps to Python
(https://docs.discord.com/developers/reference#nullable-and-optional-resource-fields):

| Discord docs        | Meaning                     | Shoal annotation                       |
| ------------------- | --------------------------- | -------------------------------------- |
| `field: type`       | always present, never null  | `field: T`                             |
| `field: ?type`      | always present, may be null | `field: T | None`                      |
| `field?: type`      | may be absent               | `field: T | UnsetType = UNSET`         |
| `field?: ?type`     | may be absent or null       | `field: T | UnsetType | None = UNSET`  |

`UNSET` (absent) and `None` (explicit null) stay distinct, so an update payload can tell "leave it"
from "clear it" — the distinction discord.py collapses.
"""

from typing import ClassVar, dataclass_transform, override

import msgspec


@dataclass_transform(kw_only_default=True, field_specifiers=(msgspec.field,))
class _PayloadMeta(msgspec.StructMeta):
    """Makes every payload keyword-only and untracked by the cycle collector by default.

    msgspec reads struct options per class, so without this every subclass would have to repeat
    `kw_only=True, gc=False`. Keyword-only lets fields keep Discord's documented order even when an
    optional field comes before a required one.
    """

    def __new__(  # noqa: PYI034 - pyright rejects Self as a metaclass return type
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        /,
        *,
        kw_only: bool = True,
        gc: bool = False,
        frozen: bool = False,
        omit_defaults: bool = False,
        tag: str | int | bool | None = None,
        tag_field: str | None = None,
    ) -> "_PayloadMeta":
        """Create a payload class with Shoal's defaults unless overridden."""
        return super().__new__(
            mcls,
            name,
            bases,
            namespace,
            kw_only=kw_only,
            gc=gc,
            frozen=frozen,
            omit_defaults=omit_defaults,
            tag=tag,
            tag_field=tag_field,
        )


@dataclass_transform(kw_only_default=True, field_specifiers=(msgspec.field,))
class Payload(msgspec.Struct, metaclass=_PayloadMeta):
    """A typed mirror of one Discord JSON object.

    Payloads hold data only: no methods that call Discord, no references to a client. Unknown fields
    Discord adds later are ignored on decode, so new API fields never break a running bot.

    A payload that holds a credential names it in `REDACTED_FIELDS`, and its repr shows
    `<redacted>` in its place, so logging the object or capturing it in an error tracker never
    leaks the secret.
    """

    REDACTED_FIELDS: ClassVar[frozenset[str]] = frozenset()
    """Fields whose value the repr hides."""

    @override
    def __repr__(self) -> str:
        shown = (
            f"{name}={'<redacted>' if name in self.REDACTED_FIELDS else repr(getattr(self, name))}"
            for name in self.__struct_fields__
        )
        return f"{type(self).__name__}({', '.join(shown)})"
