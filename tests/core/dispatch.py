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
