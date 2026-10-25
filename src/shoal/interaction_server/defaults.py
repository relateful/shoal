"""Shoal's own HTTP interaction server defaults. Nothing here is defined anywhere else."""

from typing import Final

HANDLER_TIMEOUT: Final = 10.0
"""Seconds a handler may run before the server gives up on it and replies 500. Discord has failed the
interaction long before this; the limit stops a hung handler holding a connection, and shutdown, open."""

HOST: Final = "127.0.0.1"
"""Where the server listens. Put it behind a reverse proxy with TLS; Discord only calls HTTPS URLs."""

PATH: Final = "/interactions"
"""The URL path Discord posts interactions to."""

PORT: Final = 8080
"""The port the server listens on."""
