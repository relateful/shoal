import msgspec

from shoal.payloads import AttachmentRequest, CreateMessageParams
from shoal.rest.files import File
from shoal.rest.requester import encode_query, form_of, query_of, with_attachments


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


def test_files_are_named_and_described_unless_attachments_are_given() -> None:
    files = [File("a.png", b"a", description="first"), File("b.txt", b"b", spoiler=True)]
    params, named = with_attachments(CreateMessageParams(content="hi"), files)
    assert list(named) == ["files[0]", "files[1]"]
    assert params.attachments == [
        AttachmentRequest(id=0, filename="a.png", description="first"),
        AttachmentRequest(id=1, filename="SPOILER_b.txt"),
    ]
    keep = [AttachmentRequest(id="12345"), AttachmentRequest(id=0)]
    params, _ = with_attachments(CreateMessageParams(attachments=keep), files[:1])
    assert params.attachments == keep


def test_no_files_leaves_the_params_alone() -> None:
    params = CreateMessageParams(content="hi")
    assert with_attachments(params, []) == (params, {})
