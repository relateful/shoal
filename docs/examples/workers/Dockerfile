# Built from the root of the Shoal repository (see docker-compose.yml). Shoal comes from PyPI; to
# run an unreleased change, copy `pyproject.toml`, `README.md`, `LICENSE`, `CHANGELOG.md` and `src`
# and install ".[zstd]" instead.
# One image for the three roles; docker-compose.yml picks the role with its command.
FROM python:3.12-slim

RUN pip install --no-cache-dir --pre "shoal[zstd]"

WORKDIR /app
COPY docs/examples/workers/app ./app
RUN useradd --create-home bot && mkdir /sessions && chown bot /sessions
USER bot
