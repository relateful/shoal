"""What a Components V2 message shows: text, thumbnails, media galleries, files and separators.

    class Status(ui.LayoutView):
        header = ui.TextDisplay("## Server status")
        gallery = ui.MediaGallery("https://example.com/graph.png")
        divider = ui.Separator()
        footer = ui.TextDisplay("-# Updated every minute")

Media is a URL, or a `File` sent with the message (shown as `attachment://<filename>`).

Discord: https://docs.discord.com/developers/components/reference#text-display
"""

from typing import ClassVar, override

from msgspec import UNSET

from shoal.models.base import unset_if_none
from shoal.payloads.api import ATTACHMENT_SCHEME
from shoal.payloads.components import (
    MEDIA_DESCRIPTION_MAX_LENGTH,
    MEDIA_GALLERY_MAX_ITEMS,
    FileComponent,
    MediaGalleryItem,
    SeparatorSpacing,
    UnfurledMediaItem,
)
from shoal.payloads.components import MediaGallery as MediaGalleryPayload
from shoal.payloads.components import Separator as SeparatorPayload
from shoal.payloads.components import TextDisplay as TextDisplayPayload
from shoal.payloads.components import Thumbnail as ThumbnailPayload
from shoal.rest.files import File as Upload
from shoal.ui.item import Item, check_count, check_length

type Media = str | Upload
"""A URL, or a file sent with the same message."""


def media_url(media: Media) -> str:
    """The URL a component gives for `media`: the URL itself, or the file's `attachment://` URI."""
    return media if isinstance(media, str) else media.uri


class TextDisplay(Item):
    """Markdown text, like a message's content.

    Discord: https://docs.discord.com/developers/components/reference#text-display
    """

    __slots__ = ("content",)

    is_v2: ClassVar[bool] = True

    def __init__(self, content: str, *, id: int | None = None) -> None:
        """Text shown as a message would show `content`."""
        super().__init__(id=id)
        self.content: str = content

    @override
    def to_component(self) -> TextDisplayPayload:
        """The text as Discord takes it."""
        return TextDisplayPayload(id=unset_if_none(self.id), content=self.content)

    @override
    def __repr__(self) -> str:
        return f"<TextDisplay content={self.content[:30]!r}>"


class Thumbnail(Item):
    """A small image, beside a section's text.

    Discord: https://docs.discord.com/developers/components/reference#thumbnail
    """

    __slots__ = ("description", "media", "spoiler")

    is_v2: ClassVar[bool] = True

    def __init__(
        self, media: Media, *, description: str | None = None, spoiler: bool = False, id: int | None = None
    ) -> None:
        """A thumbnail of `media`, with alt text `description` (up to 1024 characters)."""
        super().__init__(id=id)
        self.media: str = media_url(media)
        self.description: str | None = description
        self.spoiler: bool = spoiler

    @override
    def validate(self) -> None:
        super().validate()
        check_length(self, "description", self.description, MEDIA_DESCRIPTION_MAX_LENGTH)

    @override
    def to_component(self) -> ThumbnailPayload:
        """The thumbnail as Discord takes it."""
        return ThumbnailPayload(
            id=unset_if_none(self.id),
            media=UnfurledMediaItem(url=self.media),
            description=unset_if_none(self.description),
            spoiler=self.spoiler or UNSET,
        )

    @override
    def __repr__(self) -> str:
        return f"<Thumbnail media={self.media!r}>"


class MediaGallery(Item):
    """One to ten images or videos in a grid.

    Discord: https://docs.discord.com/developers/components/reference#media-gallery
    """

    __slots__ = ("items",)

    is_v2: ClassVar[bool] = True

    def __init__(self, *items: Media | MediaGalleryItem, id: int | None = None) -> None:
        """A gallery of `items`: URLs, files sent with the message, or `MediaGalleryItem`s."""
        super().__init__(id=id)
        self.items: list[MediaGalleryItem] = [
            item
            if isinstance(item, MediaGalleryItem)
            else MediaGalleryItem(media=UnfurledMediaItem(url=media_url(item)))
            for item in items
        ]

    def add_item(self, media: Media, *, description: str | None = None, spoiler: bool = False) -> None:
        """Add an image or video, with alt text `description` (up to 1024 characters)."""
        self.items.append(
            MediaGalleryItem(
                media=UnfurledMediaItem(url=media_url(media)),
                description=unset_if_none(description),
                spoiler=spoiler or UNSET,
            )
        )

    @override
    def validate(self) -> None:
        super().validate()
        check_count(self, "items", len(self.items), 1, MEDIA_GALLERY_MAX_ITEMS)
        for item in self.items:
            description = item.description if isinstance(item.description, str) else None
            check_length(self, "an item's description", description, MEDIA_DESCRIPTION_MAX_LENGTH)

    @override
    def to_component(self) -> MediaGalleryPayload:
        """The gallery as Discord takes it."""
        return MediaGalleryPayload(id=unset_if_none(self.id), items=list(self.items))

    @override
    def __repr__(self) -> str:
        return f"<MediaGallery items={len(self.items)}>"


class File(Item):
    """A file sent with the message, shown where the component is.

    Discord: https://docs.discord.com/developers/components/reference#file
    """

    __slots__ = ("media", "spoiler")

    is_v2: ClassVar[bool] = True

    def __init__(self, media: Upload | str, *, spoiler: bool = False, id: int | None = None) -> None:
        """Show `media`: a file sent with the message, or its `attachment://<filename>`."""
        super().__init__(id=id)
        self.media: str = media_url(media)
        self.spoiler: bool = spoiler

    @override
    def validate(self) -> None:
        super().validate()
        if not self.media.startswith(ATTACHMENT_SCHEME):
            msg = f"{self!r}: a file component shows a file sent with the message ({ATTACHMENT_SCHEME}...)"
            raise ValueError(msg)

    @override
    def to_component(self) -> FileComponent:
        """The file as Discord takes it."""
        return FileComponent(
            id=unset_if_none(self.id), file=UnfurledMediaItem(url=self.media), spoiler=self.spoiler or UNSET
        )

    @override
    def __repr__(self) -> str:
        return f"<File media={self.media!r}>"


class Separator(Item):
    """Space between components, with a line across unless `visible` is false.

    Discord: https://docs.discord.com/developers/components/reference#separator
    """

    __slots__ = ("spacing", "visible")

    is_v2: ClassVar[bool] = True

    def __init__(
        self,
        *,
        visible: bool = True,
        spacing: SeparatorSpacing = SeparatorSpacing.SMALL,
        id: int | None = None,
    ) -> None:
        """A separator; `visible` draws the line, `spacing` sets the padding."""
        super().__init__(id=id)
        self.visible: bool = visible
        self.spacing: SeparatorSpacing = spacing

    @override
    def to_component(self) -> SeparatorPayload:
        """The separator as Discord takes it."""
        return SeparatorPayload(id=unset_if_none(self.id), divider=self.visible, spacing=self.spacing)

    @override
    def __repr__(self) -> str:
        return f"<Separator visible={self.visible} spacing={self.spacing.name}>"
