"""REST without a bot running: post an announcement, then send and edit through a webhook.

Useful from cron jobs, CI, dashboards and workers: no gateway, no events, just requests.
"""

import asyncio
import os

from shoal.payloads import (
    AllowedMentions,
    CreateMessageParams,
    CreateWebhookParams,
    Embed,
    EmbedField,
    ExecuteWebhookParams,
)
from shoal.payloads.webhook import EditWebhookMessageParams
from shoal.rest import RestClient, Token

CHANNEL_ID = int(os.environ["CHANNEL_ID"])


async def main() -> None:
    async with RestClient(Token.bot(os.environ["DISCORD_TOKEN"])) as rest:
        me = await rest.users.get_me()
        print(f"Running as {me.username}, created {me.id.created_at:%Y-%m-%d}")

        # A message as the bot, mentioning nobody whatever the text says.
        release = Embed(
            title="v2.0 is out",
            description="Faster, smaller, typed.",
            color=0x57F287,
            fields=[EmbedField(name="Upgrade", value="`pip install -U shoal`")],
        )
        await rest.messages.create(
            CHANNEL_ID,
            CreateMessageParams(
                content="@everyone news!", embeds=[release], allowed_mentions=AllowedMentions.none()
            ),
        )

        # A webhook posts under any name and avatar, and can edit what it sent later.
        hook = await rest.webhooks.create(CHANNEL_ID, CreateWebhookParams(name="Deploys"))
        token = hook.token if isinstance(hook.token, str) else ""
        sent = await rest.webhooks.execute(
            hook.id, token, ExecuteWebhookParams(content="⏳ Deploying build 1234…", username="CI"), wait=True
        )
        # `wait=True` returns the message sent, so it can be edited.
        await rest.webhooks.edit_message(
            hook.id, token, sent.id, EditWebhookMessageParams(content="✅ Build 1234 deployed.")
        )
        await rest.webhooks.delete(hook.id)


asyncio.run(main())
