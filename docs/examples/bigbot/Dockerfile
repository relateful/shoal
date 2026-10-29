# Built from the root of the Shoal repository (see docker-compose.yml). Shoal comes from PyPI; to
# run an unreleased change, copy `pyproject.toml`, `README.md`, `LICENSE`, `CHANGELOG.md` and `src`
# and install ".[prometheus,zstd]" instead.
FROM python:3.12-slim

RUN pip install --no-cache-dir --pre "shoal[prometheus,zstd]"

WORKDIR /app
COPY docs/examples/bigbot/bigbot ./bigbot
# Runs as an unprivileged user; /data holds the sessions and the cache snapshot.
RUN useradd --create-home bot && mkdir /data && chown bot /data
USER bot
CMD ["python", "-u", "-m", "bigbot"]
