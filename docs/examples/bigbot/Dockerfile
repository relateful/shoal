# Built from the root of the Shoal repository (see docker-compose.yml), so the image installs this
# clone of Shoal. Once Shoal is on PyPI, `pip install "shoal[prometheus,zstd]"` replaces the first part.
FROM python:3.12-slim

WORKDIR /shoal
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[prometheus,zstd]"

WORKDIR /app
COPY docs/examples/bigbot/bigbot ./bigbot
# Runs as an unprivileged user; /data holds the sessions and the cache snapshot.
RUN useradd --create-home bot && mkdir /data && chown bot /data
USER bot
CMD ["python", "-u", "-m", "bigbot"]
