"""Verifying that an HTTP interaction really came from Discord.

Discord signs every request with the application's Ed25519 key over the `X-Signature-Timestamp`
header followed by the raw body. An endpoint must reject anything that fails the check with a 401;
Discord sends deliberately invalid requests to confirm it does, and stops using an endpoint that
accepts them.

Discord: https://docs.discord.com/developers/interactions/overview#setting-up-an-endpoint-validating-security-request-headers
"""

from typing import final

from shoal.core.errors import MissingDependencyError

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError as error:  # pragma: no cover - exercised only without the extra installed
    _FEATURE = "HTTP interactions"
    raise MissingDependencyError(_FEATURE, "interactions") from error


@final
class SignatureVerifier:
    """Checks request signatures against an application's public key.

    Args:
        public_key: The application's public key, as the hex string the Developer Portal shows.

    Raises:
        ValueError: `public_key` is not a 32-byte hex-encoded Ed25519 key.
    """

    __slots__ = ("_key",)

    def __init__(self, public_key: str) -> None:
        """Load the key; see the class docstring for the arguments."""
        try:
            raw = bytes.fromhex(public_key)
        except ValueError as error:
            msg = "the application public key must be hex, as shown in the Developer Portal"
            raise ValueError(msg) from error
        if len(raw) != 32:  # noqa: PLR2004 - the size of every Ed25519 public key
            msg = f"an Ed25519 public key is 32 bytes, got {len(raw)}"
            raise ValueError(msg)
        self._key: Ed25519PublicKey = Ed25519PublicKey.from_public_bytes(raw)

    def verify(self, *, signature: str, timestamp: str, body: bytes) -> bool:
        """Whether `signature` (the `X-Signature-Ed25519` header) signs `timestamp` + `body`."""
        try:
            raw_signature = bytes.fromhex(signature)
            signed = timestamp.encode() + body
        except ValueError:  # not hex, or a header aiohttp decoded into lone surrogates
            return False
        try:
            self._key.verify(raw_signature, signed)
        except InvalidSignature:
            return False
        return True
