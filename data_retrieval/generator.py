import asyncio
import os
import sys

os.environ["PROJECT_NAME"] = 'cryptocurrency_analysis/'
REQUIRED_VARS = ["WALLEX_TOPIC", 'CMP_TOPIC', 'BROKER_URL', 'LOG_LEVEL']
missing_vars = [var for var in REQUIRED_VARS if var not in os.environ]

if missing_vars:
    print(f"Error: The following required environment variables are missing: {', '.join(missing_vars)}",
          file=sys.stderr)
    sys.exit(1)

PROJECT_NAME = os.getenv('PROJECT_NAME')
ROOT_DIR = str(str(os.path.realpath(__file__).replace('\\', '/')).split(PROJECT_NAME)[0]) + PROJECT_NAME
sys.path.append(ROOT_DIR)

from data_retrieval.crypto_currency_api import CryptoCurrencyApi
from logger import logger_

if __name__ == '__main__':
    logger_.info('generator started')
    api = CryptoCurrencyApi()
    asyncio.run(api.run())
