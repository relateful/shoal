import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from shoal.interaction_server.signature import SignatureVerifier
from tests.support.signing import PUBLIC, sign

BODY = b'{"type":1}'


def test_a_genuine_signature_verifies() -> None:
    verifier = SignatureVerifier(PUBLIC)
    assert verifier.verify(signature=sign("1700000000", BODY), timestamp="1700000000", body=BODY)


def test_hex_case_does_not_matter() -> None:
    verifier = SignatureVerifier(PUBLIC.upper())
    signature = sign("1700000000", BODY).upper()
    assert verifier.verify(signature=signature, timestamp="1700000000", body=BODY)


def test_anything_altered_fails() -> None:
    verifier = SignatureVerifier(PUBLIC)
    signature = sign("1700000000", BODY)
    assert not verifier.verify(signature=signature, timestamp="1700000001", body=BODY)
    assert not verifier.verify(signature=signature, timestamp="1700000000", body=b'{"type":2}')
    assert not verifier.verify(signature="zz", timestamp="1700000000", body=BODY)
    assert not verifier.verify(signature="", timestamp="", body=BODY)
    assert not verifier.verify(signature="00" * 10, timestamp="1700000000", body=BODY)
    other = Ed25519PrivateKey.generate().sign(b"1700000000" + BODY).hex()
    assert not verifier.verify(signature=other, timestamp="1700000000", body=BODY)


def test_headers_that_are_not_text_fail_instead_of_raising() -> None:
    # aiohttp decodes header bytes that are not UTF-8 into lone surrogates, which cannot be encoded.
    verifier = SignatureVerifier(PUBLIC)
    signature = sign("1700000000", BODY)
    assert not verifier.verify(signature=signature, timestamp="1700000000\udcff", body=BODY)
    assert not verifier.verify(signature=signature + "\udcff", timestamp="1700000000", body=BODY)


def test_bad_keys_are_rejected_up_front() -> None:
    with pytest.raises(ValueError, match="hex"):
        SignatureVerifier("not hex")
    with pytest.raises(ValueError, match="32 bytes"):
        SignatureVerifier("abcd")
