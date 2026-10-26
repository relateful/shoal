"""Receive interactions over HTTP instead of the gateway (`pip install 'shoal[interactions]'`).

An app that only uses commands and components needs no gateway connection at all: Discord posts each
interaction to a public HTTPS URL. `Endpoint` verifies Discord's signature, answers `PING`,
and passes everything else to your handler. It can run on its own or mount onto an existing aiohttp
application, such as a dashboard's backend, with `install`.

Discord: https://docs.discord.com/developers/interactions/overview#configuring-an-interactions-endpoint-url
"""

from shoal.endpoint import defaults
from shoal.endpoint.server import Endpoint, EndpointHandler
from shoal.endpoint.signature import SignatureVerifier

__all__ = ["Endpoint", "EndpointHandler", "SignatureVerifier", "defaults"]
