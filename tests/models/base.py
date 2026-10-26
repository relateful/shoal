from datetime import UTC, datetime

import pytest

from shoal.core.snowflake import Snowflake
from shoal.models.base import MISSING, Hashable, MissingType, Object


def test_objects_compare_and_hash_by_id() -> None:
    assert Object(5) == Object(5)
    assert Object(5) != Object(6)
    assert len({Object(5), Object(5), Object(6)}) == 2
    assert Object(5).id == Snowflake(5)
    assert repr(Object(5)) == "<Object id=5>"


def test_creation_time_comes_from_the_id() -> None:
    moment = datetime(2024, 1, 1, tzinfo=UTC)
    assert Object(Snowflake.from_datetime(moment)).created_at == moment


def test_different_model_types_are_never_equal() -> None:
    class Other(Object):
        __slots__ = ()

    assert Other(5) != Object(5)
    assert hash(Other(5)) != hash(Object(5))


def test_a_model_without_an_id_says_so() -> None:
    with pytest.raises(NotImplementedError):
        _ = Hashable().id


def test_missing_is_one_sentinel() -> None:
    assert isinstance(MISSING, MissingType)
