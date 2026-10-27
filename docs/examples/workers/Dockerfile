# Built from the root of the Shoal repository (see docker-compose.yml), so the image installs this
# clone of Shoal. Once Shoal is on PyPI, `pip install "shoal[zstd]"` replaces the first part.
# One image for the three roles; docker-compose.yml picks the role with its command.
FROM python:3.12-slim

WORKDIR /shoal
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[zstd]"

WORKDIR /app
COPY docs/examples/workers/app ./app
RUN useradd --create-home bot && mkdir /sessions && chown bot /sessions
USER bot
