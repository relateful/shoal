from shoal.models.state import State
from tests.support.fakes import FakeTransport
from tests.support.models import ROW_VIEW
from tests.support.rest import make_client


def identity(state: State) -> tuple[int | None, int | None]:
    """Read through a function: checkers narrow properties across calls."""
    return state.user_id, state.application_id


def test_identity_is_unknown_until_recorded() -> None:
    state = State(rest=make_client(FakeTransport()))
    assert identity(state) == (None, None)
    state.identify(user_id=1, application_id=7)
    assert identity(state) == (1, 7)


def test_without_a_registry_views_are_dropped_quietly() -> None:
    state = State(rest=make_client(FakeTransport()))
    state.views.store(ROW_VIEW, message_id=5)
    assert state.cache.revision == 0
