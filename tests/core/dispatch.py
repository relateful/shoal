import msgspec

from shoal.core.dispatch import DispatchEvent
from shoal.payloads import User


def test_dispatch_event_decodes_its_raw_data() -> None:
    event = DispatchEvent(
        0,
        "X",
        1,
        msgspec.Raw(b'{"id":"5","username":"a","discriminator":"0","global_name":null,"avatar":null}'),
    )
    assert event.decode(User).id == 5


def test_each_type_is_decoded_once_and_shared() -> None:
    event = DispatchEvent(0, "X", 1, msgspec.Raw(b'{"a": 1}'))
    first = event.decode(dict[str, int])
    assert event.decode(dict[str, int]) is first
    assert event.decode(dict[str, float]) is not first
    assert event == DispatchEvent(0, "X", 1, msgspec.Raw(b'{"a": 1}'))
    assert "_decoded" not in repr(event)
