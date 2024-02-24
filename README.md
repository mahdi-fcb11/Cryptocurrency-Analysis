# Cryptocurrency Analysis

[![Python 3.8](https://img.shields.io/badge/Python-3.8-green.svg)](https://shields.io/)
[![PySpark](https://img.shields.io/badge/PySpark-3.5-blue.svg)](https://shields.io/)
[![Kafka](https://img.shields.io/badge/Confluent_Kafka-7.3.3-green.svg)](https://shields.io/)
[![MinIO](https://img.shields.io/badge/MinIO-2023/12/23-blue.svg)](https://shields.io/)

This project gets cryptocurrency data from CoinMarketCap and Wallex APIs, analyzes them and saves them in MinIO.

## Usage

Instructions on how to run the project and the structure of the project is documented in here.

## Development Setup

The project is fully dockerized. it can be run simply by building the Dockerfile and running docker-compose.

```shell
docker-compose up
```

The first docker-compose runs kafka, kafka-ui, minio, and spark containers. 

Then we should run the following commands in order to create topics in kafka.

```shell
docker exec -it broker kafka-topics --bootstrap-server localhost:9093 --create --topic coin_market_cap --partitions 1 --replication-factor 1 --config cleanup.policy=delete,compact --config min.cleanable.dirty.ratio=0.001 --config segment.ms=10000 --config max.compaction.lag.ms=10000 --config retention.ms=172800000
docker exec -it broker kafka-topics --bootstrap-server localhost:9093 --create --topic wallex --partitions 1 --replication-factor 1 --config cleanup.policy=delete --config retention.ms=172800000
```

In order to create buckets in minio we run the following commands.

```shell
docker exec -it minio mc mb /mnt/data/spark
docker exec -it minio mc mb /mnt/data/lake-house
```

For the next part to work, we need to create an access key through minio in http://localhost:9601 and update the environment variables for MINIO_ACC_KEY and MINIO_SEC_KEY in docker-compose-crypto.yml.
Now for running the project in order to gather data from CoinMarketCap and Wallex we will run the following command.

```shell
docker build -t crypto:latest .
docker-compose -f docker-compose-crypto.yml up generator
```

Now if we want to process the gathered data and save them in minio, we will run the following command.

```shell
docker-compose -f docker-compose-crypto.yml up processor 
```

This container submits the application spark and shows the result. It also saves the result in minio.

In order to have access to spark shell we can run the following command.

```shell
docker run -it crypto:latest bash
```

## Python Scripts

The code for this project contains of two parts, gathering the data and processing them. The following schema shows the project structure.

```text
├── data_retrieval               <- data gathering package
│   ├── aio_producer.py          <- confluent kafka multi-thread producer
│   ├── crypto_currency_api.py   <- api class for calling CoinMarketCap and Wallex APIs
│   ├── generator.py             <- the main python file that calls the APIs and sends them through producer
│   └── logger.py                <- utility logger for better logging in console
├── processor.py                 <- main python file that has to be submitted into spark
├── docker-compose.yml           <- docker-compose for kafka, kafka-ui, minio, and spark
├── docker-compose-crypto.yml    <- docker-compose for generating or processing the data using spark
├── Dockerfile                   <- Dockerfile for project
├── entrypoint.sh                <- entrypoint for Dockerfile 
└── update_run.sh                <- necessary file for kraft configuration in confluent-kafka
```

### How It Works

Data retrieval package is the first step of this project. generator.py file calls functions from crypto_currency_api.py 
to gather information every minute from the two mentioned websites. It will run for three hours and captures data every 
minute and sends it to kafka topic through functions in aio_producer.py.

The second step of the projects runs with spark-submit on processor.py file, with the following command in container's bash

```shell
spark-submit --master spark://spark-master:7077 --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4 processor.py
```

We have two streams from our kafka topics, which should be joined. We use spark structured streaming to join these streams.
These streams are ordered, so we define a short-term watermark for both of them.
Our two streams are joined with the condition that their time fields are within 30 seconds of each other. After joining,
we calculate base_tmn field and partition_key field. Then data will be transferred to s3 bucket. 
The data will be retrieved again from MinIO for further process. 
We perform two different kind of calculations on our data. First, for each 10 minutes open, close, avg, max, min price 
are calculated and saved into candles_df.
Second, based on available coins, we calculate total market cap based on USD. 
These two dataframe will be writen to s3 in parquet format.

We can also use batch programing, but according to [Why Streaming and RunOnce is Better than Batch](https://www.databricks.com/blog/2017/05/22/running-streaming-jobs-day-10x-cost-savings.html)
we leveraged streaming approach. Run once is a better approach for triggering a pipeline between long intervals.

### Data partitioning
We repartition and then write the data based on their types. As the data is growing, accessing recent data will not overhead resources.
The main dataframes were partitioned based on the coin and the date of data creation.

## Configurations

### Kafka Configurations 

Data gathered from websites every one minute are uploaded into two different kafka topics.

1. coin_market_cap: This topic keeps api results from CoinMarketCap website.
2. wallex: This topic keeps api results from Wallex website.

CoinMarketCap api documents mention that the data will be cached for 5 minutes, meaning we may have duplicate data that can fill up our storage and make the data process heavy.
In order to handle this caching we use two retention policies for this site's kafka topic, ASAP compact and delete after two days. 
But the retention policy for wallex topic is only set to delete after two days, for it seems to be live.

Other configurations for kafka topics are in the following:
- max.compaction.lag.ms: 10,000 (10sec)
- min.cleanable.dirty.ratio: 0
- segment.ms: 10,000(10sec)
- retention.ms: 172800000 (2days)

### MinIO Configuration

There are no special configurations for setting up MinIO. We set both MINO_ROOT_USER and MINIO_ROOT_PASSWORD to minioadmin. 
Then we have to create an access key through http://localhost:9601 and set environment variables of MINIO_ACC_KEY and MINIO_SEC_KEY in docker-compose-crypto.yml.

### Spark Container

We used bitnami spark image to deploy standalone cluster with a master node and a slave node.
Then we submit the processor.py into our spark cluster.

## Author

Mahdi Zarei Yazd
