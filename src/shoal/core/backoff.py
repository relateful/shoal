"""The one backoff formula Shoal uses for retries and reconnects."""

import random


def backoff_delay(attempt: int, *, cap: float, random_source: random.Random) -> float:
    """Seconds to wait before retry number `attempt` (1-based).

    Exponential growth (1, 2, 4, 8 ... seconds) capped at `cap`, with "equal jitter": half the delay
    is fixed and half is random, so many clients failing at once do not retry in lockstep.

    Raises:
        ValueError: `attempt` is below 1 or `cap` is not positive.
    """
    if attempt < 1:
        msg = "attempt must be at least 1"
        raise ValueError(msg)
    if cap <= 0:
        msg = "cap must be positive"
        raise ValueError(msg)
    ceiling = min(cap, 2.0 ** min(attempt - 1, 62))
    return ceiling / 2 + random_source.random() * ceiling / 2
