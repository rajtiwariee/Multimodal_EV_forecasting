import json
import logging
import os
import time
from datetime import datetime

import pandas as pd
from kafka import KafkaProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC = "rides"

# Path to your processed Parquet files (adjust if your structure is different)
# This script assumes it's run from the project root or can find the data path.
PARQUET_FILE_PATH_TEMPLATE = "./data/warehouse/city=sample_city/year={year}/month={month:02d}/rides.parquet"


def get_rides_from_parquet(year, month):
    """Loads ride data from a Parquet file for a given year and month."""
    file_path = PARQUET_FILE_PATH_TEMPLATE.format(year=year, month=month)
    if not os.path.exists(file_path):
        logger.warning(f"Parquet file not found: {file_path}")
        return pd.DataFrame()  # Return empty DataFrame if file not found
    try:
        df = pd.read_parquet(file_path)
        # Ensure 'start_time' is datetime, it should be from your Airflow DAG
        if "start_time" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["start_time"]):
            df["start_time"] = pd.to_datetime(df["start_time"])
        return df
    except Exception as e:
        logger.error(f"Error reading Parquet file {file_path}: {e}")
        return pd.DataFrame()


def create_kafka_producer():
    """Creates and returns a Kafka producer."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        logger.info(f"Kafka producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
        return producer
    except Exception as e:
        logger.error(f"Failed to connect Kafka producer: {e}")
        raise


def simulate_rides(producer, rides_df, speed_factor=60):
    """Simulates sending ride events to Kafka.
    Sorts rides by start_time and sends them out, simulating passage of time.
    `speed_factor`: How much faster than real-time to simulate.
                   1 = real-time, 60 = 1 minute of real rides per second of simulation.
                   A large value means rides are sent out quickly with small delays.
    """
    if rides_df.empty or "start_time" not in rides_df.columns:
        logger.info("No rides to simulate or 'start_time' column missing.")
        return

    rides_df = rides_df.sort_values(by="start_time").reset_index(drop=True)

    logger.info(f"Starting simulation of {len(rides_df)} ride events...")

    # To simulate realistic timestamps, we can either:
    # 1. Use the historical timestamps directly if just replaying.
    # 2. Adjust historical timestamps to be "around now" for a more "live" feel.
    # For this simulator, let's primarily focus on the *sequence* and *delay* between events.
    # We'll send the historical record as is.

    last_simulated_time = None

    for index, row in rides_df.iterrows():
        ride_event = row.to_dict()

        # Convert datetime/timestamp objects to string for JSON serialization
        for key, value in ride_event.items():
            if isinstance(value, pd.Timestamp | datetime):
                ride_event[key] = value.isoformat()
            elif pd.isna(value):  # Handle NaT or NaN
                ride_event[key] = None

        current_event_time = pd.to_datetime(ride_event["start_time"])

        if last_simulated_time:
            # Calculate time difference from previous event in the data
            time_diff_real = (current_event_time - last_simulated_time).total_seconds()

            # Calculate scaled sleep time
            sleep_time_simulated = max(0, time_diff_real / speed_factor)

            if sleep_time_simulated > 0:
                logger.debug(f"Sleeping for {sleep_time_simulated:.2f} seconds to simulate time between rides.")
                time.sleep(sleep_time_simulated)

        try:
            producer.send(KAFKA_TOPIC, value=ride_event)
            logger.info(f"Sent ride event {index + 1}/{len(rides_df)}: ride_id {ride_event.get('ride_id', 'N/A')}")
        except Exception as e:
            logger.error(f"Error sending message to Kafka: {e}")

        last_simulated_time = current_event_time

        # Small fixed delay to prevent overwhelming Kafka for very dense events or high speed_factor
        time.sleep(0.01)

    producer.flush()
    logger.info("All ride events simulated and flushed to Kafka.")


if __name__ == "__main__":
    # --- Configuration for which data to simulate ---
    # For example, simulate rides from January 2022
    sim_year = 2022
    sim_month = 1
    simulation_speed = 3600  # 1 hour of rides per second (very fast for testing)
    # or 60 for 1 minute of rides per second
    # or 1 for "real-time" replay (could be very slow)

    logger.info(f"Loading ride data for {sim_year}-{sim_month:02d}...")
    rides_to_simulate = get_rides_from_parquet(year=sim_year, month=sim_month)

    if not rides_to_simulate.empty:
        kafka_producer = create_kafka_producer()
        if kafka_producer:
            try:
                simulate_rides(kafka_producer, rides_to_simulate, speed_factor=simulation_speed)
            finally:
                kafka_producer.close()
                logger.info("Kafka producer closed.")
    else:
        logger.info(f"No ride data found for {sim_year}-{sim_month:02d} to simulate.")
