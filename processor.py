import sys
import os
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, \
    TimestampType, FloatType, DoubleType
from pyspark.sql import functions as F, Window
from pyspark import SparkContext


os.environ["PROJECT_NAME"] = 'cryptocurrency_analysis/'
REQUIRED_VARS = ["WALLEX_TOPIC", 'CMP_TOPIC', 'BROKER_URL', 'MINIO_ACC_KEY', 'MINIO_SEC_KEY', 'DEST_URL', 'MINIO_URL']
missing_vars = [var for var in REQUIRED_VARS if var not in os.environ]

if missing_vars:
    print(f"Error: The following required environment variables are missing: {', '.join(missing_vars)}",
          file=sys.stderr)
    sys.exit(1)


WALLEX_TOPIC = os.getenv('WALLEX_TOPIC')
CMP_TOPIC = os.getenv('CMP_TOPIC')
KAFKA_BOOTSTRAP_SERVERS = os.getenv('BROKER_URL')
minio_url = os.getenv('MINIO_URL')
minio_access_key = os.getenv('MINIO_ACC_KEY')
minio_secret_key = os.getenv('MINIO_SEC_KEY')
write_url = os.getenv('DEST_URL')


def load_config(spark_context: SparkContext):
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.access.key",
                                                 os.getenv("AWS_ACCESS_KEY_ID", minio_access_key))
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.secret.key",
                                                 os.getenv("AWS_SECRET_ACCESS_KEY", minio_secret_key))
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.endpoint", minio_url)
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.connection.ssl.enabled", "true")
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.path.style.access", "true")
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.attempts.maximum", "1")
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.connection.establish.timeout", "5000")
    spark_context._jsc.hadoopConfiguration().set("fs.s3a.connection.timeout", "10000")


spark = (
    SparkSession.builder.appName("Crypto data processing")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")
load_config(spark.sparkContext)

SCHEMA_WALLEX = StructType([
    StructField("wallex_symbol", StringType(), nullable=False),
    StructField("wallex_base", StringType(), nullable=False),
    StructField("wallex_quote", StringType(), nullable=False),
    StructField("wallex_price", FloatType(), nullable=False),
    StructField("wallex_last_updated", TimestampType(), nullable=False)
])

SCHEMA_CMP = StructType([
    StructField("cmp_symbol", StringType(), nullable=False),
    StructField("cmp_base", StringType(), nullable=False),
    StructField("cmp_quote", StringType(), nullable=False),
    StructField("cmp_price", FloatType(), nullable=False),
    StructField("cmp_market_cap", FloatType(), nullable=False),
    StructField("cmp_last_updated", TimestampType(), nullable=False)
])


if __name__ == "__main__":
    df_wallex = (spark
                 .readStream
                 .format("kafka")
                 .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
                 .option("subscribe", WALLEX_TOPIC)
                 .option("startingOffsets", "earliest")
                 .load()
                 )

    df_cmp = (spark
              .readStream
              .format("kafka")
              .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
              .option("subscribe", CMP_TOPIC)
              .option("startingOffsets", "earliest")
              .load()
              )

    df_wallex = df_wallex.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)", "timestamp") \
        .select(F.from_json('value', SCHEMA_WALLEX).alias("value")) \
        .select('value.*') \
        .withWatermark("wallex_last_updated", "10 minutes")

    df_cmp = df_cmp.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)", "timestamp") \
        .select(F.from_json('value', SCHEMA_CMP).alias("value")) \
        .select('value.*') \
        .withWatermark("cmp_last_updated", "10 minutes")

    df_joined = df_cmp.join(
        df_wallex,
        F.expr("""
        wallex_base = cmp_quote AND
        wallex_last_updated + INTERVAL 30 seconds > cmp_last_updated AND
        wallex_last_updated - INTERVAL 30 seconds <= cmp_last_updated
        """))

    df_joined = df_joined.withColumn('base_price_tmn', df_joined.cmp_price * df_joined.wallex_price) \
        .drop('cmp_symbol', 'wallex_symbol') \
        .withColumn('partition_key', F.date_trunc('day', 'wallex_last_updated'))

    df_joined.repartition('cmp_base', 'partition_key').writeStream.partitionBy('partition_key', 'cmp_base') \
        .format('parquet').option("path", write_url + "cmp_tmn.parquet") \
        .option("checkpointLocation", "s3a://spark/cmp-tmn/checkpoints") \
        .trigger(once=True) \
        .start().awaitTermination()

    df = spark.read.parquet(write_url + "cmp_tmn.parquet")
    # df.show(truncate=False)
    df_market_cap = df.groupBy('cmp_last_updated').agg(F.sum('cmp_market_cap').alias('total_market_cap')) \
        .withColumn('partition_key', F.date_trunc('day', 'cmp_last_updated')) \
        .orderBy('cmp_last_updated')

    df = df.withColumn('group_base', F.window('wallex_last_updated', '10 minutes'))
    window_spec = Window.partitionBy("cmp_base", 'group_base')
    df_with_row_number = df.withColumn(
        "close_index", F.row_number().over(window_spec.orderBy(df["wallex_last_updated"].desc()))) \
        .withColumn(
        "open_index", F.row_number().over(window_spec.orderBy(df["wallex_last_updated"])))

    df_agg = df.groupBy(
        F.col('cmp_base').alias('base'), 'group_base', F.col('wallex_quote').alias('quote')).agg(
        F.max('base_price_tmn').alias('max_price'),
        F.min('base_price_tmn').alias('min_price'),
        F.avg('base_price_tmn').alias('avg_price')
    )
    df_close = df_with_row_number.filter(df_with_row_number.close_index == 1).select(
        F.col('cmp_base').alias('base'), F.col('base_price_tmn').alias('open_price'), 'group_base',
        F.col('wallex_quote').alias('quote'))
    df_open = df_with_row_number.filter(df_with_row_number.open_index == 1).select(
        F.col('cmp_base').alias('base'), F.col('base_price_tmn').alias('close_price'), 'group_base',
        F.col('wallex_quote').alias('quote'))
    df_candles = df_close.join(
        df_open, ['group_base', 'base', 'quote'])

    df_candles = df_candles.join(df_agg, ['group_base', 'base', 'quote']) \
        .withColumn('partition_key', F.date_trunc('day', 'group_base.start'))

    df_market_cap.repartition('partition_key') \
        .write.mode("overwrite").partitionBy('partition_key').parquet(write_url + 'market_cap.parquet')
    df_candles.repartition('partition_key') \
        .write.mode("overwrite").partitionBy('partition_key').parquet(write_url + 'candles.parquet')
    df_market_cap.show(5, truncate=False)
    df_candles.show(5, truncate=False)
