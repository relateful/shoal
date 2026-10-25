"""An Ed25519 key pair standing in for an application's, to sign HTTP interactions as Discord does."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

KEY = Ed25519PrivateKey.generate()
PUBLIC = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def sign(timestamp: str, body: bytes) -> str:
    """The `X-Signature-Ed25519` header Discord would send with `timestamp` and `body`."""
    return KEY.sign(timestamp.encode() + body).hex()
