# Dashboards and REST

`RestClient` needs no gateway and no cache, so a web backend can use it directly.

```python
from shoal.rest import RestClient, Token

async with RestClient(Token.bearer(oauth_access_token)) as rest:
    me = await rest.users.get_me()
```

- `Token.bot(...)` acts as the bot; `Token.bearer(...)` acts as an OAuth2 user.
- `base_url=` points the client at a REST proxy, so several processes share one set of rate limits.
- Every error is typed and derives from `HTTPError`, which carries Discord's error `code`:
  `BadRequestError` (400), `UnauthorizedError` (401), `ForbiddenError` (403), `NotFoundError` (404),
  `RateLimitedError` (a 429 longer than `max_rate_limit_wait`) and `ServerError` (5xx).
  `TokenInvalidatedError` is raised for every request after a bot token was rejected, and
  `ClientClosedError` after `close()`.

## Files and images

Methods that send a message take `files=`: messages, webhooks, interaction responses, follow-ups
and forum posts. Shoal sends the request as `multipart/form-data` and describes each file in
`attachments`. A sticker upload takes its one file as `file=`.

```python
from shoal.payloads import CreateMessageParams
from shoal.rest import File

report = await File.from_path("report.png", description="Weekly report")  # read off the event loop
await rest.messages.create(channel_id, CreateMessageParams(content="This week"), files=[report])
```

`File.from_path` guesses the content type from the extension; pass `content_type=` to set it.

When editing a message, the files passed are added and the existing attachments stay. To remove
some, list the ones to keep in `attachments` by ID; Shoal adds the new files to that list for you.
Alt text on a new file is only sent when `attachments` is listed this way.

```python
from shoal.payloads import AttachmentRequest, EditMessageParams

keep = [AttachmentRequest(id=str(attachment.id)) for attachment in message.attachments[:1]]
await rest.messages.edit(channel_id, message.id, EditMessageParams(attachments=keep), files=[report])
```

Fields that take an image or a sound inline (an avatar, an emoji, a soundboard sound) take a data URI:
`image_data(png_bytes)` and `sound_data(ogg_bytes)` from `shoal.payloads` build one and check the
format.

## Webhooks

`Webhook` sends through a webhook's URL. Sending and editing need only the webhook's token, so a
script with no bot token can post:

```python
from shoal import Embed
from shoal.models import Webhook
from shoal.rest import RestClient

async with RestClient(None) as rest:
    webhook = Webhook.from_url(webhook_url, rest=rest)
    message = await webhook.send(embed=Embed(title="Deploying"), username="CI", wait=True)
    await message.edit(embed=Embed(title="Deployed"))
```

Without `wait=True`, Discord does not confirm the message and `send` returns `None`. In a forum
channel, pass `thread_name=` to start a post, or `thread=` to send in one.

## Rate limits that protect your IP

- Requests are bucketed by Discord's `X-RateLimit-Bucket` and the route's top-level resource.
- A global limiter keeps the bot under 50 requests per second.
- Discord temporarily restricts an IP after 10,000 responses with 401, 403 or 429 in ten minutes. Shoal
  counts them and holds requests back before the limit, and with a bot token it stops sending after
  the first 401, because a revoked token makes every request invalid.

## Searching messages

```python
from shoal.payloads import SearchMessagesParams, SearchHasType, excluding

result = await rest.messages.search(
    guild_id,
    SearchMessagesParams(content="release", has=[SearchHasType.LINK, excluding(SearchHasType.IMAGE)]),
)
for message in result.matches:
    ...
```

If Discord is still indexing the guild it answers `202 Accepted`; the client waits the time Discord
asks for and retries, then raises `SearchIndexNotReadyError`.
