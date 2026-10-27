"""Settings shared by the three processes, read from the environment."""

import os
import sys


def required(name: str) -> str:
    """The variable's value; exits with a clear message when it is missing."""
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"{name} is not set (copy .env.example to .env and fill it in)")
    return value


GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "127.0.0.1")
"""Where the gateway process streams events (its IPC server)."""
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "7700"))
PROXY_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:8080/api")
"""Where the REST proxy listens; every process sends its REST requests there."""
WORKER_SHARDS = [int(shard) for shard in os.environ.get("WORKER_SHARDS", "").split(",") if shard]
"""The shards this worker handles; empty for all. Split shards between workers to spread the load."""
