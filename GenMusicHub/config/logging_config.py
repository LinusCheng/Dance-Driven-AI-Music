import logging
import sys


LOG_FORMAT = '[GenMusicHub] %(asctime)s %(levelname)s: %(message)s'
LOG_DATE_FORMAT = '%H:%M:%S'


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def configure_logging(verbose: bool) -> None:
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(MaxLevelFilter(logging.INFO))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.handlers = [stdout_handler, stderr_handler]

    logging.getLogger('GenMusicHub.mrt2_realtime').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('GenMusicHub.magenta_engine').setLevel(logging.DEBUG if verbose else logging.INFO)
