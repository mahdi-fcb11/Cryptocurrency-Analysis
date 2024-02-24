#!/bin/bash

current_datetime="runtime: "$(date +"%Y-%m-%dT%H:%M:%S")
echo $current_datetime

if [ $# -eq 0 ]; then
    echo "No command provided. Exiting."
    sleep 5
    exit 1
elif [ "$1" == "generator" ]; then
  python3 data_retrieval/generator.py

elif [ "$1" == "processor" ]; then
  spark-submit --master spark://spark-master:7077 --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4 processor.py

elif [ "$1" == "bash" ]; then
  exec /bin/bash

else
    echo "Invalid argument. Exiting..."
    sleep 3
    exit 1
fi
