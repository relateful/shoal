"""`python -m bigbot`: read the settings, set up logging, run until stopped."""

import logging
import sys

from bigbot.bot import BigBot
from bigbot.config import ConfigError, Settings


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        sys.exit(f"bigbot: {error}")
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    BigBot(settings).run(settings.token, log_level=None)  # logging is set up above


main()
