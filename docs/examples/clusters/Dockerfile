# Built from the root of the Shoal repository (see docker-compose.yml), so the image installs this
# clone of Shoal. Once Shoal is on PyPI, `pip install "shoal[redis,zstd]"` replaces the first part.
FROM python:3.12-slim

WORKDIR /shoal
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[redis,zstd]"

WORKDIR /app
COPY docs/examples/clusters/cluster ./cluster
RUN useradd --create-home bot
USER bot
CMD ["python", "-u", "-m", "cluster"]
