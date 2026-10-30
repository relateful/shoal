"""A builder for embeds.

    embed = Embed(title="Server stats", colour=0x5865F2)
    embed.add_field(name="Members", value="1,024").set_footer(text="Updated hourly")
    await channel.send(embed=embed)

Discord: https://docs.discord.com/developers/resources/message#embed-object
"""

from datetime import datetime
from typing import Self, final, override

import msgspec
from msgspec import UNSET, UnsetType

from shoal.core.codec import JSONObject, decode_json, encode_json
from shoal.models.base import unset_if_none
from shoal.models.colour import Colour
from shoal.payloads.message import Embed as EmbedPayload
from shoal.payloads.message import EmbedAuthor, EmbedField, EmbedFooter, EmbedImage, EmbedProvider, EmbedVideo


def _value[T](value: T | UnsetType) -> T | None:
    return None if isinstance(value, UnsetType) else value


@final
class Embed:
    """An embed you build and send, or read from a received message.

    Every setter returns the embed, so calls chain. `colour` and `color` are the same thing.

    Discord: https://docs.discord.com/developers/resources/message#embed-object
    """

    __slots__ = ("_data",)

    def __init__(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        url: str | None = None,
        colour: int | None = None,
        color: int | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Start an embed; add the rest with the `set_*` and `add_field` methods."""
        chosen = colour if colour is not None else color
        self._data: EmbedPayload = EmbedPayload(
            title=unset_if_none(title),
            description=unset_if_none(description),
            url=unset_if_none(url),
            color=unset_if_none(chosen),
            timestamp=unset_if_none(timestamp),
        )

    @classmethod
    def from_payload(cls, payload: EmbedPayload) -> Self:
        """An embed holding a received payload, such as one of `message.embeds`."""
        embed = cls()
        embed._data = payload
        return embed

    @classmethod
    def from_dict(cls, data: JSONObject) -> Self:
        """An embed from its JSON form.

        Raises:
            PayloadDecodeError: `data` is not an embed.
        """
        return cls.from_payload(decode_json(encode_json(data), EmbedPayload))

    def to_payload(self) -> EmbedPayload:
        """The embed as it is sent."""
        return self._data

    def to_dict(self) -> JSONObject:
        """The embed's JSON form."""
        decoded: JSONObject = msgspec.json.decode(encode_json(self._data))
        return decoded

    @property
    def title(self) -> str | None:
        """The title."""
        return _value(self._data.title)

    @title.setter
    def title(self, value: str | None) -> None:
        self._data = msgspec.structs.replace(self._data, title=unset_if_none(value))

    @property
    def description(self) -> str | None:
        """The text under the title."""
        return _value(self._data.description)

    @description.setter
    def description(self, value: str | None) -> None:
        self._data = msgspec.structs.replace(self._data, description=unset_if_none(value))

    @property
    def url(self) -> str | None:
        """Where the title links to."""
        return _value(self._data.url)

    @url.setter
    def url(self, value: str | None) -> None:
        self._data = msgspec.structs.replace(self._data, url=unset_if_none(value))

    @property
    def colour(self) -> int | None:
        """The colour of the left border, as a `Colour`."""
        color = _value(self._data.color)
        return None if color is None else Colour(color)

    @colour.setter
    def colour(self, value: int | None) -> None:
        self._data = msgspec.structs.replace(self._data, color=unset_if_none(value))

    color = colour

    @property
    def timestamp(self) -> datetime | None:
        """The time shown in the footer."""
        return _value(self._data.timestamp)

    @timestamp.setter
    def timestamp(self, value: datetime | None) -> None:
        self._data = msgspec.structs.replace(self._data, timestamp=unset_if_none(value))

    @property
    def footer(self) -> EmbedFooter | None:
        """The footer."""
        return _value(self._data.footer)

    @property
    def image(self) -> EmbedImage | None:
        """The large image."""
        return _value(self._data.image)

    @property
    def thumbnail(self) -> EmbedImage | None:
        """The small image at the top right."""
        return _value(self._data.thumbnail)

    @property
    def video(self) -> EmbedVideo | None:
        """The video, on embeds Discord generated from a link."""
        return _value(self._data.video)

    @property
    def provider(self) -> EmbedProvider | None:
        """The site, on embeds Discord generated from a link."""
        return _value(self._data.provider)

    @property
    def author(self) -> EmbedAuthor | None:
        """The author line."""
        return _value(self._data.author)

    @property
    def fields(self) -> list[EmbedField]:
        """The fields, in order."""
        return list(_value(self._data.fields) or [])

    def set_footer(self, *, text: str | None = None, icon_url: str | None = None) -> Self:
        """Set the footer, or remove it when `text` is `None`."""
        footer = UNSET if text is None else EmbedFooter(text=text, icon_url=unset_if_none(icon_url))
        self._data = msgspec.structs.replace(self._data, footer=footer)
        return self

    def remove_footer(self) -> Self:
        """Remove the footer."""
        return self.set_footer()

    def set_image(self, *, url: str | None) -> Self:
        """Set the large image, or remove it with `None`."""
        self._data = msgspec.structs.replace(self._data, image=UNSET if url is None else EmbedImage(url=url))
        return self

    def set_thumbnail(self, *, url: str | None) -> Self:
        """Set the small image, or remove it with `None`."""
        thumbnail = UNSET if url is None else EmbedImage(url=url)
        self._data = msgspec.structs.replace(self._data, thumbnail=thumbnail)
        return self

    def set_author(self, *, name: str, url: str | None = None, icon_url: str | None = None) -> Self:
        """Set the author line."""
        author = EmbedAuthor(name=name, url=unset_if_none(url), icon_url=unset_if_none(icon_url))
        self._data = msgspec.structs.replace(self._data, author=author)
        return self

    def remove_author(self) -> Self:
        """Remove the author line."""
        self._data = msgspec.structs.replace(self._data, author=UNSET)
        return self

    def add_field(self, *, name: str, value: str, inline: bool = True) -> Self:
        """Add a field at the end."""
        return self._set_fields([*self.fields, EmbedField(name=name, value=value, inline=inline)])

    def insert_field_at(self, index: int, *, name: str, value: str, inline: bool = True) -> Self:
        """Insert a field before `index`."""
        fields = self.fields
        fields.insert(index, EmbedField(name=name, value=value, inline=inline))
        return self._set_fields(fields)

    def set_field_at(self, index: int, *, name: str, value: str, inline: bool = True) -> Self:
        """Replace the field at `index`.

        Raises:
            IndexError: There is no field at `index`.
        """
        fields = self.fields
        fields[index] = EmbedField(name=name, value=value, inline=inline)
        return self._set_fields(fields)

    def remove_field(self, index: int) -> Self:
        """Remove the field at `index`; an index past the end does nothing."""
        fields = self.fields
        if -len(fields) <= index < len(fields):
            del fields[index]
        return self._set_fields(fields)

    def clear_fields(self) -> Self:
        """Remove every field."""
        return self._set_fields([])

    def _set_fields(self, fields: list[EmbedField]) -> Self:
        self._data = msgspec.structs.replace(self._data, fields=fields or UNSET)
        return self

    def __len__(self) -> int:
        """The characters that count toward Discord's 6,000 per message.

        Those are the title, description, field names and values, footer text and author name.
        """
        total = len(self.title or "") + len(self.description or "")
        total += sum(len(field.name) + len(field.value) for field in self.fields)
        total += len(self.footer.text) if self.footer else 0
        total += len(self.author.name) if self.author else 0
        return total

    @override
    def __repr__(self) -> str:
        return f"<Embed title={self.title!r} fields={len(self.fields)}>"
