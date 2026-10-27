"""`python -m cluster`: read the settings, set up logging, run this cluster until stopped."""

import logging
import sys

from cluster.bot import ClusterBot
from cluster.config import ConfigError, Settings


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        sys.exit(f"cluster: {error}")
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s %(levelname)-8s {settings.name} %(name)s: %(message)s",
        stream=sys.stdout,
    )
    ClusterBot(settings).run(settings.token, log_level=None)


main()
