# Built from the root of the Shoal repository (see docker-compose.yml). Shoal comes from PyPI; to
# run an unreleased change, copy `pyproject.toml`, `README.md`, `LICENSE`, `CHANGELOG.md` and `src`
# and install ".[redis,zstd]" instead.
FROM python:3.12-slim

RUN pip install --no-cache-dir --pre "shoal[redis,zstd]"

WORKDIR /app
COPY docs/examples/clusters/cluster ./cluster
RUN useradd --create-home bot
USER bot
CMD ["python", "-u", "-m", "cluster"]
