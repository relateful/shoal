from shoal.payloads import CreateStickerParams, EditStickerParams
from shoal.rest.files import File
from tests.support.json_payloads import USER
from tests.support.multipart import FormPart
from tests.support.rest import EndpointCase, check_endpoint, endpoint_cases

STANDARD: dict[str, object] = {
    "id": "749054660769218631",
    "name": "Wave",
    "tags": "wumpus, hello, sup, hi",
    "type": 1,
    "format_type": 3,
    "description": "Wumpus waves hello",
    "pack_id": "847199849233514549",
    "sort_value": 12,
}
"""Discord's example, with fewer tags."""
GUILD_STICKER: dict[str, object] = {
    "id": "8",
    "name": "party",
    "description": None,
    "tags": "tada",
    "type": 2,
    "format_type": 1,
    "available": True,
    "guild_id": "2",
    "user": USER,
}
PACK: dict[str, object] = {
    "id": "847199849233514549",
    "stickers": [STANDARD],
    "name": "Wumpus Beyond",
    "sku_id": "847199849233514547",
    "cover_sticker_id": "749053689419006003",
    "description": "Say hello to Wumpus!",
    "banner_asset_id": "761773777976819732",
}
PNG = b"\x89PNG\r\n\x1a\n"

CASES = [
    EndpointCase(
        name="get sticker",
        call=lambda client: client.stickers.get_any(749054660769218631),
        method="GET",
        path="/stickers/749054660769218631",
        response=STANDARD,
    ),
    EndpointCase(
        name="list packs",
        call=lambda client: client.stickers.list_packs(),
        method="GET",
        path="/sticker-packs",
        response={"sticker_packs": [PACK]},
        result=[PACK],
    ),
    EndpointCase(
        name="get pack",
        call=lambda client: client.stickers.get_pack(847199849233514549),
        method="GET",
        path="/sticker-packs/847199849233514549",
        response=PACK,
    ),
    EndpointCase(
        name="list guild stickers",
        call=lambda client: client.stickers.list(2),
        method="GET",
        path="/guilds/2/stickers",
        response=[GUILD_STICKER],
    ),
    EndpointCase(
        name="get guild sticker",
        call=lambda client: client.stickers.get(2, 8),
        method="GET",
        path="/guilds/2/stickers/8",
        response=GUILD_STICKER,
    ),
    EndpointCase(
        name="create guild sticker",
        call=lambda client: client.stickers.create(
            2,
            CreateStickerParams(name="party", description="", tags="tada"),
            File("party.png", PNG, content_type="image/png"),
            reason="new sticker",
        ),
        method="POST",
        path="/guilds/2/stickers",
        files=(
            FormPart("name", None, "text/plain", b"party"),
            FormPart("description", None, "text/plain", b""),
            FormPart("tags", None, "text/plain", b"tada"),
            FormPart("file", "party.png", "image/png", PNG),
        ),
        response=GUILD_STICKER,
        reason="new sticker",
    ),
    EndpointCase(
        name="modify guild sticker",
        call=lambda client: client.stickers.edit(2, 8, EditStickerParams(description=None)),
        method="PATCH",
        path="/guilds/2/stickers/8",
        body={"description": None},
        response=GUILD_STICKER,
    ),
    EndpointCase(
        name="delete guild sticker",
        call=lambda client: client.stickers.delete(2, 8),
        method="DELETE",
        path="/guilds/2/stickers/8",
    ),
]


@endpoint_cases(CASES)
async def test_sticker_endpoints(case: EndpointCase) -> None:
    await check_endpoint(case)
