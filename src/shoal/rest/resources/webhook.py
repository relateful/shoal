"""Endpoints for webhooks and the messages they send.

The `with_token` variants, and executing and editing messages, need only the webhook's token: they
work without a bot token, so a `RestClient(None)` can use them.

Discord: https://docs.discord.com/developers/resources/webhook
"""

import builtins
from collections.abc import Mapping, Sequence
from typing import Literal, overload

from shoal.payloads.message import Message
from shoal.payloads.webhook import (
    CreateWebhookParams,
    EditWebhookMessageParams,
    EditWebhookParams,
    EditWebhookWithTokenParams,
    ExecuteWebhookParams,
    Webhook,
)
from shoal.rest.endpoints import (
    CREATE_WEBHOOK,
    DELETE_WEBHOOK,
    DELETE_WEBHOOK_MESSAGE,
    DELETE_WEBHOOK_WITH_TOKEN,
    EDIT_WEBHOOK_MESSAGE,
    EXECUTE_GITHUB_COMPATIBLE_WEBHOOK,
    EXECUTE_SLACK_COMPATIBLE_WEBHOOK,
    EXECUTE_WEBHOOK,
    GET_CHANNEL_WEBHOOKS,
    GET_GUILD_WEBHOOKS,
    GET_WEBHOOK,
    GET_WEBHOOK_MESSAGE,
    GET_WEBHOOK_WITH_TOKEN,
    MODIFY_WEBHOOK,
    MODIFY_WEBHOOK_WITH_TOKEN,
)
from shoal.rest.files import File
from shoal.rest.requester import QueryValue, Resource, with_attachments


def _query(
    *, wait: bool | None = None, thread_id: int | None = None, with_components: bool | None = None
) -> dict[str, QueryValue] | None:
    """The webhook query parameters that were given, or `None` for an empty query."""
    query: dict[str, QueryValue] = {}
    if wait is not None:
        query["wait"] = wait
    if thread_id is not None:
        query["thread_id"] = thread_id
    if with_components is not None:
        query["with_components"] = with_components
    return query or None


class Webhooks(Resource):
    """Webhooks, executing them, and their messages.

    Use it as `rest.webhooks`, where `rest` is a `RestClient`.
    """

    __slots__ = ()

    async def create(
        self, channel_id: int, params: CreateWebhookParams, *, reason: str | None = None
    ) -> Webhook:
        """Create an incoming webhook in a channel. Needs Manage Webhooks.

        Discord: https://docs.discord.com/developers/resources/webhook#create-webhook
        """
        return await self.request(
            CREATE_WEBHOOK.compile(channel_id=channel_id), Webhook, body=params, reason=reason
        )

    async def list_for_channel(self, channel_id: int) -> builtins.list[Webhook]:
        """List a channel's webhooks. Needs Manage Webhooks.

        Discord: https://docs.discord.com/developers/resources/webhook#get-channel-webhooks
        """
        return await self.request(GET_CHANNEL_WEBHOOKS.compile(channel_id=channel_id), list[Webhook])

    async def list(self, guild_id: int) -> builtins.list[Webhook]:
        """List a guild's webhooks. Needs Manage Webhooks.

        Discord: https://docs.discord.com/developers/resources/webhook#get-guild-webhooks
        """
        return await self.request(GET_GUILD_WEBHOOKS.compile(guild_id=guild_id), list[Webhook])

    async def get(self, webhook_id: int) -> Webhook:
        """Get a webhook. Needs Manage Webhooks, unless the app owns it.

        Discord: https://docs.discord.com/developers/resources/webhook#get-webhook
        """
        return await self.request(GET_WEBHOOK.compile(webhook_id=webhook_id), Webhook)

    async def get_with_token(self, webhook_id: int, webhook_token: str) -> Webhook:
        """Get a webhook by its token, without a bot token. `user` is not returned.

        Discord: https://docs.discord.com/developers/resources/webhook#get-webhook-with-token
        """
        return await self.request(
            GET_WEBHOOK_WITH_TOKEN.compile(webhook_id=webhook_id, webhook_token=webhook_token), Webhook
        )

    async def edit(self, webhook_id: int, params: EditWebhookParams, *, reason: str | None = None) -> Webhook:
        """Rename a webhook, change its avatar or move it. Needs Manage Webhooks.

        Discord: https://docs.discord.com/developers/resources/webhook#modify-webhook
        """
        return await self.request(
            MODIFY_WEBHOOK.compile(webhook_id=webhook_id), Webhook, body=params, reason=reason
        )

    async def edit_with_token(
        self,
        webhook_id: int,
        webhook_token: str,
        params: EditWebhookWithTokenParams,
    ) -> Webhook:
        """Rename a webhook or change its avatar by its token, without a bot token.

        Discord: https://docs.discord.com/developers/resources/webhook#modify-webhook-with-token
        """
        return await self.request(
            MODIFY_WEBHOOK_WITH_TOKEN.compile(webhook_id=webhook_id, webhook_token=webhook_token),
            Webhook,
            body=params,
        )

    async def delete(self, webhook_id: int, *, reason: str | None = None) -> None:
        """Delete a webhook for good. Needs Manage Webhooks.

        Discord: https://docs.discord.com/developers/resources/webhook#delete-webhook
        """
        await self.request_empty(DELETE_WEBHOOK.compile(webhook_id=webhook_id), reason=reason)

    async def delete_with_token(self, webhook_id: int, webhook_token: str) -> None:
        """Delete a webhook by its token, without a bot token.

        Discord: https://docs.discord.com/developers/resources/webhook#delete-webhook-with-token
        """
        await self.request_empty(
            DELETE_WEBHOOK_WITH_TOKEN.compile(webhook_id=webhook_id, webhook_token=webhook_token),
        )

    @overload
    async def execute(
        self,
        webhook_id: int,
        webhook_token: str,
        params: ExecuteWebhookParams,
        *,
        wait: Literal[False] = False,
        thread_id: int | None = None,
        with_components: bool = False,
        files: Sequence[File] = (),
    ) -> None: ...

    @overload
    async def execute(
        self,
        webhook_id: int,
        webhook_token: str,
        params: ExecuteWebhookParams,
        *,
        wait: Literal[True],
        thread_id: int | None = None,
        with_components: bool = False,
        files: Sequence[File] = (),
    ) -> Message: ...

    @overload
    async def execute(
        self,
        webhook_id: int,
        webhook_token: str,
        params: ExecuteWebhookParams,
        *,
        wait: bool,
        thread_id: int | None = None,
        with_components: bool = False,
        files: Sequence[File] = (),
    ) -> Message | None: ...

    async def execute(
        self,
        webhook_id: int,
        webhook_token: str,
        params: ExecuteWebhookParams,
        *,
        wait: bool = False,
        thread_id: int | None = None,
        with_components: bool = False,
        files: Sequence[File] = (),
    ) -> Message | None:
        """Send a message through a webhook.

        With `wait`, Discord confirms the message and returns it; without, a message that fails to
        save is not reported. `thread_id` posts in a thread of the webhook's channel; in a forum or
        media channel, pass it or `params.thread_name`. `with_components` lets a webhook the app does
        not own send non-interactive components.

        Discord: https://docs.discord.com/developers/resources/webhook#execute-webhook
        """
        route = EXECUTE_WEBHOOK.compile(webhook_id=webhook_id, webhook_token=webhook_token)
        query = _query(wait=wait or None, thread_id=thread_id, with_components=with_components or None)
        body, named = with_attachments(params, files)
        if wait:
            return await self.request(route, Message, body=body, query=query, files=named)
        await self.request_empty(route, body=body, query=query, files=named)
        return None

    async def execute_slack(
        self,
        webhook_id: int,
        webhook_token: str,
        payload: Mapping[str, object],
        *,
        thread_id: int | None = None,
        wait: bool | None = None,
    ) -> None:
        """Post a Slack incoming-webhook payload; Discord's default for `wait` is true here.

        Discord does not support Slack's `channel`, `icon_emoji`, `mrkdwn` or `mrkdwn_in`.

        Discord: https://docs.discord.com/developers/resources/webhook#execute-slack-compatible-webhook
        """
        await self.request_empty(
            EXECUTE_SLACK_COMPATIBLE_WEBHOOK.compile(webhook_id=webhook_id, webhook_token=webhook_token),
            body=payload,
            query=_query(wait=wait, thread_id=thread_id),
        )

    async def execute_github(
        self,
        webhook_id: int,
        webhook_token: str,
        payload: Mapping[str, object],
        *,
        thread_id: int | None = None,
        wait: bool | None = None,
    ) -> None:
        """Post a GitHub webhook event payload; Discord's default for `wait` is true here.

        Discord: https://docs.discord.com/developers/resources/webhook#execute-github-compatible-webhook
        """
        await self.request_empty(
            EXECUTE_GITHUB_COMPATIBLE_WEBHOOK.compile(webhook_id=webhook_id, webhook_token=webhook_token),
            body=payload,
            query=_query(wait=wait, thread_id=thread_id),
        )

    async def get_message(
        self, webhook_id: int, webhook_token: str, message_id: int, *, thread_id: int | None = None
    ) -> Message:
        """Get a message the webhook sent.

        Discord: https://docs.discord.com/developers/resources/webhook#get-webhook-message
        """
        return await self.request(
            GET_WEBHOOK_MESSAGE.compile(
                webhook_id=webhook_id, webhook_token=webhook_token, message_id=message_id
            ),
            Message,
            query=_query(thread_id=thread_id),
        )

    async def edit_message(
        self,
        webhook_id: int,
        webhook_token: str,
        message_id: int,
        params: EditWebhookMessageParams,
        *,
        thread_id: int | None = None,
        with_components: bool = False,
        files: Sequence[File] = (),
    ) -> Message:
        """Edit a message the webhook sent; files passed are added to it.

        Discord: https://docs.discord.com/developers/resources/webhook#edit-webhook-message
        """
        body, named = with_attachments(params, files, edit=True)
        return await self.request(
            EDIT_WEBHOOK_MESSAGE.compile(
                webhook_id=webhook_id, webhook_token=webhook_token, message_id=message_id
            ),
            Message,
            body=body,
            query=_query(thread_id=thread_id, with_components=with_components or None),
            files=named,
        )

    async def delete_message(
        self, webhook_id: int, webhook_token: str, message_id: int, *, thread_id: int | None = None
    ) -> None:
        """Delete a message the webhook sent.

        Discord: https://docs.discord.com/developers/resources/webhook#delete-webhook-message
        """
        await self.request_empty(
            DELETE_WEBHOOK_MESSAGE.compile(
                webhook_id=webhook_id, webhook_token=webhook_token, message_id=message_id
            ),
            query=_query(thread_id=thread_id),
        )
