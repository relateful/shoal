from datetime import UTC, datetime

import msgspec
import pytest
from msgspec import UNSET

from shoal.payloads import AttachmentRequest, CreateMessageParams, EditMessageParams
from shoal.rest.files import File
from shoal.rest.requester import comma_joined, encode_query, form_of, query_of, with_attachments


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


def test_edits_add_new_files_to_the_attachments_the_caller_keeps() -> None:
    files = [File("a.png", b"a", description="alt")]
    params, _ = with_attachments(
        EditMessageParams(attachments=[AttachmentRequest(id="12345")]), files, edit=True
    )
    assert params.attachments == [
        AttachmentRequest(id="12345"),
        AttachmentRequest(id=0, filename="a.png", description="alt"),
    ]
    # Without a list, the existing attachments stay and Discord adds the files.
    params, named = with_attachments(EditMessageParams(content="x"), files, edit=True)
    assert params.attachments is UNSET
    assert list(named) == ["files[0]"]
    # An entry the caller already wrote for the file is left as it is.
    own = [AttachmentRequest(id=0, description="mine")]
    assert with_attachments(EditMessageParams(attachments=own), files, edit=True)[0].attachments == own


def test_comma_joined_lists_skip_an_empty_list() -> None:
    assert comma_joined({"include_roles": [1, 2], "days": 7}, "include_roles") == {
        "days": 7,
        "include_roles": "1,2",
    }
    assert comma_joined({"include_roles": [], "days": 7}, "include_roles") == {"days": 7}
    assert comma_joined({"days": 7}, "include_roles") == {"days": 7}


class Untyped(msgspec.Struct, kw_only=True):
    value: object = msgspec.UNSET


@pytest.mark.parametrize("value", [None, [[1]], 1.5], ids=["null", "nested list", "float"])
def test_queries_refuse_values_they_cannot_carry(value: object) -> None:
    with pytest.raises(TypeError, match="value cannot be sent in a query"):
        query_of(Untyped(value=value))


def test_forms_refuse_values_they_cannot_carry() -> None:
    with pytest.raises(TypeError, match="value cannot be sent as text"):
        form_of(Untyped(value=[1]))
    assert form_of(Untyped(value=datetime(2026, 1, 1, tzinfo=UTC))) == {"value": "2026-01-01T00:00:00+00:00"}
