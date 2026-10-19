import logging
from datetime import datetime

from tqdm import tqdm


class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
        except Exception:
            self.handleError(record)


def set_logger():
    logger = logging.getLogger("pandapower")

    # Remove the existing console handler
    logger.handlers.clear()

    handler = TqdmLoggingHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)


dates: list[datetime] = []


def pbar_date_postfix(i, time_step, time_steps, **kwargs):
    pbar = kwargs["ts_variables"]["progress_bar"]
    pbar.set_postfix_str(str(dates[i]))
