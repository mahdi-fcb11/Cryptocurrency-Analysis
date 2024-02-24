import logging
import os
from datetime import datetime

PROJECT_NAME = os.getenv('PROJECT_NAME')
ROOT_DIR = str(str(os.path.realpath(__file__).replace('\\', '/')).split(PROJECT_NAME)[0]) + PROJECT_NAME

LOG_LEVEL = os.getenv('LOG_LEVEL')
if LOG_LEVEL not in ('ERROR', 'DEBUG', 'INFO', 'WARNING', 'CRITICAL'):
    LOG_LEVEL = 'INFO'


def get_logger(module_name):
    logger = logging.getLogger(name=module_name)
    if logger.hasHandlers():
        logger.handlers.clear()
    formatter = logging.Formatter('%(levelname)s:     %(asctime)s, %(name)s %(message)s')

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.setLevel(LOG_LEVEL)

    logger.addHandler(stream_handler)
    logger.debug('logger configured')
    return logger


logger_ = get_logger(PROJECT_NAME)
