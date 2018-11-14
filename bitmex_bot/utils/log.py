import logging
from bitmex_bot.settings import settings


def setup_custom_logger(name, log_level=settings.LOG_LEVEL):
    formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(handler)

    fh = logging.FileHandler('log/info.log')
    fh.setLevel(log_level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger

def setup_OHLC_logger(name, log_level=settings.LOG_LEVEL):
    formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

    handler = logging.FileHandler('log/OHLC.log')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(handler)
    return logger


