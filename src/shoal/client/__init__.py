"""The client: events as models, interactions with `response` and `followup`.

Discord: https://docs.discord.com/developers/events/gateway
"""

from shoal.client.client import Client, ClientError, ClientOptions, InteractionHandler, Listener
from shoal.client.events import EventTranslator
from shoal.client.interaction import (
    Followup,
    Interaction,
    InteractionPayload,
    InteractionRespondedError,
    InteractionResponse,
    OptionNamespace,
    Responder,
)
from shoal.client.views import DispatchableView, SubmittableModal, ViewStore

__all__ = [
    "Client",
    "ClientError",
    "ClientOptions",
    "DispatchableView",
    "EventTranslator",
    "Followup",
    "Interaction",
    "InteractionHandler",
    "InteractionPayload",
    "InteractionRespondedError",
    "InteractionResponse",
    "Listener",
    "OptionNamespace",
    "Responder",
    "SubmittableModal",
    "ViewStore",
]
