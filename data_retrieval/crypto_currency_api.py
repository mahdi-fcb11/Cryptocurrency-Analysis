import os
import sys
from datetime import datetime
from confluent_kafka import KafkaException
import asyncio
import aiohttp
import json
from data_retrieval.aio_producer import AIOProducer
from logger import logger_
import pytz


class CryptoCurrencyApi:

    def __init__(self):
        self.urls = {
            'wallex':
                'https://api.wallex.ir/v1/markets',
            'CMP':
                'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?convert=USDT&aux=cmc_rank&limit=2'
        }
        self.headers = {
            'CMP': {
                'X-CMC_PRO_API_KEY': '4da1e482-5c67-4a85-8fc6-d3376bec629a'
            },
            'wallex': {}
        }
        self.topics = {
            'wallex': os.getenv('WALLEX_TOPIC'),
            'CMP': os.getenv('CMP_TOPIC')
        }

    async def api_call(self, source):
        for _ in range(20):
            t0 = datetime.now()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                try:
                    async with session.get(self.urls[source], headers=self.headers[source]) as response:
                        t1 = datetime.now()
                        logger_.debug(f'{source} api time: {(t1 - t0).total_seconds()}')
                        if response.status == 200:
                            result = await response.text()
                            data = json.loads(result)
                            return data
                        else:
                            logger_.error(f'{source} api call was not successful, sleep for 1 minute')
                            await asyncio.sleep(1)
                            continue
                except aiohttp.ClientError as e:
                    logger_.error(f"client error:\n {e}")
                    await asyncio.sleep(1)

            await asyncio.sleep(1)

    async def send_to_producer(self, producer, key, payload, source):
        for _ in range(20):
            t0 = datetime.now()
            try:
                result = await producer.produce(topic=self.topics[source],
                                                key=json.dumps(key),
                                                value=json.dumps(payload))
                logger_.debug({"sent successfully at ": result.timestamp()})
                t1 = datetime.now()
                logger_.debug(f'{source} send time: {(t1 - t0).total_seconds()}')
                break
            except KafkaException as ex:
                logger_.error(f'failed to send data: {ex}')
                continue

    async def wallex(self, producer=None):
        result = await self.api_call(source='wallex')
        data = result['result']['symbols']['USDTTMN']

        retrieve_datetime = datetime.now(tz=pytz.timezone('UTC')).replace(microsecond=0)
        payload = {
            'wallex_symbol': data['symbol'],
            'wallex_base': data['baseAsset'],
            'wallex_quote': data['quoteAsset'],
            'wallex_price': round(float(data['stats']['lastPrice']), 3),
            'wallex_last_updated': str(retrieve_datetime)
        }
        key = {
            'wallex_symbol': payload['wallex_symbol'],
            'wallex_last_updated': payload['wallex_last_updated']
        }
        logger_.info(f'wallex api result:\n {payload}')
        await self.send_to_producer(producer, key, payload, source='wallex')

    async def coin_market_cap(self, producer):
        data = await self.api_call(source='CMP')
        btc, eth = data['data']

        btc_updated = btc['quote']['USDT']['last_updated'].replace('Z', '+00:00')
        eth_updated = eth['quote']['USDT']['last_updated'].replace('Z', '+00:00')
        payload = {
            'BTCUSDT': {
                'cmp_symbol': f"{btc['symbol']}USDT",
                'cmp_base': btc['symbol'],
                'cmp_quote': 'USDT',
                'cmp_price': btc['quote']['USDT']['price'],
                'cmp_market_cap': btc['quote']['USDT']['market_cap'],
                'cmp_last_updated': btc_updated
            },
            'ETHUSDT': {
                'cmp_symbol': f"{eth['symbol']}USDT",
                'cmp_base': eth['symbol'],
                'cmp_quote': 'USDT',
                'cmp_price': eth['quote']['USDT']['price'],
                'cmp_market_cap': eth['quote']['USDT']['market_cap'],
                'cmp_last_updated': eth_updated
            }

        }
        key = {
            'BTCUSDT': {'BTC_updated': btc_updated},
            'ETHUSDT': {'ETH_updated': eth_updated}
        }
        logger_.info(f'CMP api result:\n {payload}')

        for payload_key in list(payload.keys()):
            await self.send_to_producer(producer, key[payload_key], payload[payload_key], source='CMP')

    async def run(self):
        producer = AIOProducer({"bootstrap.servers": os.getenv('BROKER_URL')})
        try:
            for i in range(180):
                t0 = datetime.now()
                await asyncio.gather(self.wallex(producer), self.coin_market_cap(producer))
                t1 = datetime.now()
                logger_.debug(f'total run time: {(t1 - t0).total_seconds()}')
                logger_.debug('*' * 100)
                await asyncio.sleep(60)
        finally:
            producer.close()
