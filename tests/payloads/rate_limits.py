from shoal.core import UNSET
from shoal.core.codec import decode_json
from shoal.payloads import (
    RateLimitResponse,
)


def test_rate_limit_response_reads_the_global_keyword_field() -> None:
    response = decode_json(b'{"message":"m","retry_after":1.5,"global":true}', RateLimitResponse)
    assert response.global_
    assert response.code is UNSET
