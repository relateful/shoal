import msgspec

from shoal.rest.requester import encode_query, form_of, query_of


class Filters(msgspec.Struct, kw_only=True):
    author_id: list[int] | msgspec.UnsetType = msgspec.UNSET
    pinned: bool | msgspec.UnsetType = msgspec.UNSET
    limit: int | msgspec.UnsetType = msgspec.UNSET
    content: str | msgspec.UnsetType = msgspec.UNSET


def test_queries_repeat_arrays_and_spell_booleans() -> None:
    query = encode_query({"author_id": [1, 2], "pinned": False, "content": "a b&c"})
    assert query == "author_id=1&author_id=2&pinned=false&content=a+b%26c"


def test_query_payloads_send_only_the_fields_that_are_set() -> None:
    assert query_of(Filters(author_id=[1], limit=5)) == {"author_id": [1], "limit": 5}
    assert query_of(Filters()) == {}


def test_form_payloads_send_set_fields_as_text() -> None:
    assert form_of(Filters(content="hi", limit=5, pinned=True)) == {
        "pinned": "true",
        "limit": "5",
        "content": "hi",
    }
