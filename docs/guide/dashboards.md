# Dashboards and REST

`RestClient` needs no gateway and no cache, so a web backend can use it directly.

```python
from shoal.rest import RestClient, Token

async with RestClient(Token.bearer(oauth_access_token)) as rest:
    me = await rest.get_current_user()
```

- `Token.bot(...)` acts as the bot; `Token.bearer(...)` acts as an OAuth2 user.
- `base_url=` points the client at a REST proxy, so several processes share one set of rate limits.
- Every error is typed and derives from `HTTPError`, which carries Discord's error `code`:
  `BadRequestError` (400), `UnauthorizedError` (401), `ForbiddenError` (403), `NotFoundError` (404),
  `RateLimitedError` (a 429 longer than `max_rate_limit_wait`) and `ServerError` (5xx).
  `TokenInvalidatedError` is raised for every request after a bot token was rejected, and
  `ClientClosedError` after `close()`.

## Files and images

Endpoints that take files have a `files=` argument; Shoal sends the request as `multipart/form-data`
and, for messages, describes each file in `attachments`.

```python
from shoal.payloads import CreateMessageParams
from shoal.rest import File

report = await File.from_path("report.png", description="Weekly report")  # read off the event loop
await rest.create_message(channel_id, CreateMessageParams(content="This week"), files=[report])
```

When editing a message, files passed are added to it. To remove attachments, list the ones to keep
in `attachments`.

Fields that take an image or a sound inline (an avatar, an emoji, a soundboard sound) take a data URI:
`image_data(png_bytes)` and `sound_data(ogg_bytes)` build one and check the format.

## Rate limits that protect your IP

- Requests are bucketed by Discord's `X-RateLimit-Bucket` and the route's top-level resource.
- A global limiter keeps the bot under 50 requests per second.
- Discord temporarily restricts an IP after 10,000 responses with 401, 403 or 429 in ten minutes. Shoal
  counts them and holds requests back before the limit, and with a bot token it stops sending after
  the first 401, because a revoked token makes every request invalid.

## Searching messages

```python
from shoal.payloads import SearchGuildMessagesParams, SearchHasType, excluding

result = await rest.search_guild_messages(
    guild_id,
    SearchGuildMessagesParams(content="release", has=[SearchHasType.LINK, excluding(SearchHasType.IMAGE)]),
)
for message in result.matches:
    ...
```

If Discord is still indexing the guild it answers `202 Accepted`; the client waits the time Discord
asks for and retries, then raises `SearchIndexNotReadyError`.
