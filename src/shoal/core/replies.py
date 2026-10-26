"""How code answering an interaction over HTTP learns that its reply has reached Discord.

An HTTP reply is written only after the handler returns, so a follow-up or edit sent straight after
answering would race it and find no response yet. `Endpoint` sets `REPLY_WRITTEN` while it runs a
handler; whoever hands it the response waits on the future before going on.
"""

import asyncio
from contextvars import ContextVar
from typing import Final

REPLY_WRITTEN: Final[ContextVar[asyncio.Future[None] | None]] = ContextVar(
    "shoal_reply_written", default=None
)
"""Inside an `Endpoint` handler: resolves once the HTTP reply was written, or will never be."""
