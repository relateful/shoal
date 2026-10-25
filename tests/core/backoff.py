import random

import pytest

from shoal.core.backoff import backoff_delay


@pytest.mark.parametrize(
    ("attempt", "ceiling"), [(1, 1.0), (2, 2.0), (3, 4.0), (6, 30.0), (60, 30.0), (10_000, 30.0)]
)
def test_backoff_grows_exponentially_up_to_the_cap(attempt: int, ceiling: float) -> None:
    random_source = random.Random(1)
    for _ in range(50):
        delay = backoff_delay(attempt, cap=30.0, random_source=random_source)
        assert ceiling / 2 <= delay <= ceiling


def test_backoff_validates_arguments() -> None:
    with pytest.raises(ValueError, match="attempt"):
        backoff_delay(0, cap=1.0, random_source=random.Random())
    with pytest.raises(ValueError, match="cap"):
        backoff_delay(1, cap=0.0, random_source=random.Random())
