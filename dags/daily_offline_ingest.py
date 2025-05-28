import logging
import os
from datetime import datetime, timedelta

# from airflow.utils.dates import days_ago # Replaced by pendulum for start_date
# --- Open-Meteo Specific Imports ---
import openmeteo_requests
import pandas as pd
import pendulum  # You're using this for start_date now
import requests_cache

# pyarrow is needed for to_parquet
from airflow import DAG
from airflow.operators.python import PythonOperator
from retry_requests import retry  # For resilient API calls

# --- Configuration ---
CITY_NAME = "sample_city"
RAW_DATA_BASE_PATH = f"/opt/airflow/data/raw/ride_data/{CITY_NAME}"
WAREHOUSE_BASE_PATH = f"/opt/airflow/data/warehouse/city={CITY_NAME}"

CITY_COORDINATES = {
    "sample_city": {
        "latitude": 40.7128,
        "longitude": -74.0060,
    }  # Example: NYC for sample_city
}

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


# --- Existing Ride Ingestion Function (ensure your debug prints are removed or commented if desired) ---
def ingest_ride_data_for_month(logical_date_str: str, **kwargs):
    logical_date = datetime.fromisoformat(logical_date_str)
    target_year = logical_date.year
    target_month = logical_date.month
    logging.info(f"Starting ride data ingestion for {CITY_NAME} for {target_year}-{target_month:02d}")

    input_csv_filename = f"{CITY_NAME}_rides_{target_year}_{target_month:02d}.csv"
    input_csv_path = os.path.join(RAW_DATA_BASE_PATH, input_csv_filename)

    if not os.path.exists(input_csv_path):
        logging.warning(f"Ride CSV file not found: {input_csv_path}. Skipping ride ingestion.")
        return

    logging.info(f"Reading ride CSV: {input_csv_path}")
    try:
        df = pd.read_csv(input_csv_path)
    except Exception as e:
        logging.error(f"Error reading ride CSV {input_csv_path}: {e}")
        raise

    if "start_time" in df.columns:
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    if "end_time" in df.columns:
        df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")

    df["year"] = target_year
    df["month"] = target_month

    output_dir = os.path.join(WAREHOUSE_BASE_PATH, f"year={target_year}", f"month={target_month:02d}")
    os.makedirs(output_dir, exist_ok=True)
    output_parquet_path = os.path.join(output_dir, "rides.parquet")

    logging.info(f"Writing {len(df)} ride rows to Parquet: {output_parquet_path}")
    try:
        df.to_parquet(output_parquet_path, index=False, engine="pyarrow")
    except Exception as e:
        logging.error(f"Error writing ride Parquet to {output_parquet_path}: {e}")
        raise
    logging.info(f"Successfully ingested ride data for {target_year}-{target_month:02d} into {output_parquet_path}")


# --- New Weather Fetching Function ---
def fetch_weather_for_specific_ride_days(logical_date_str: str, **kwargs):
    logical_date = datetime.fromisoformat(logical_date_str)
    target_year = logical_date.year
    target_month = logical_date.month

    logging.info(f"Starting weather fetch for specific ride days in {CITY_NAME} for {target_year}-{target_month:02d}")

    if CITY_NAME not in CITY_COORDINATES:
        logging.error(f"Coordinates for {CITY_NAME} not found. Skipping weather fetch.")
        return

    coords = CITY_COORDINATES[CITY_NAME]
    latitude = coords["latitude"]
    longitude = coords["longitude"]

    # Read the corresponding ride CSV to find unique days
    ride_csv_filename = f"{CITY_NAME}_rides_{target_year}_{target_month:02d}.csv"
    ride_csv_path = os.path.join(RAW_DATA_BASE_PATH, ride_csv_filename)

    if not os.path.exists(ride_csv_path):
        logging.warning(f"Ride CSV file not found: {ride_csv_path}. Cannot determine specific days for weather. Skipping.")
        return

    try:
        rides_df = pd.read_csv(ride_csv_path)
        # Ensure 'start_time' exists and convert to datetime, handling potential errors
        if "start_time" not in rides_df.columns:
            logging.warning(f"'start_time' column not found in {ride_csv_path}. Skipping weather fetch.")
            return
        rides_df["start_time"] = pd.to_datetime(rides_df["start_time"], errors="coerce")
        rides_df.dropna(subset=["start_time"], inplace=True)  # Drop rows where conversion failed

        unique_ride_dates_dt = rides_df["start_time"].dt.normalize().unique()
        unique_ride_dates_str = sorted([pd.Timestamp(date).strftime("%Y-%m-%d") for date in unique_ride_dates_dt])  # Sort for consistency
    except Exception as e:
        logging.error(f"Error processing ride CSV {ride_csv_path} to get unique dates: {e}")
        raise  # Raise error to fail the task if CSV processing fails

    if not unique_ride_dates_str:
        logging.info(f"No valid unique ride dates found in {ride_csv_path} after processing. Skipping weather fetch.")
        return

    logging.info(f"Found unique ride dates for weather fetch: {unique_ride_dates_str}")

    # Setup the Open-Meteo API client with cache and retry
    # Using a temporary directory for cache within the task attempt might be safer for Airflow
    # Or ensure .cache is writable by the airflow user.
    # For simplicity, default .cache in current working dir (which is /opt/airflow for the task)
    cache_session = requests_cache.CachedSession(".airflow_openmeteo_cache", expire_after=-1, use_temp=True)
    retry_session = retry(cache_session, retries=3, backoff_factor=0.5)  # Reduced retries for quicker testing
    openmeteo = openmeteo_requests.Client(session=retry_session)

    all_hourly_weather_dfs = []
    api_url = "https://archive-api.open-meteo.com/v1/archive"  # Historical API

    for ride_date_str in unique_ride_dates_str:
        logging.info(f"Fetching weather for date: {ride_date_str}")
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": ride_date_str,
            "end_date": ride_date_str,
            "hourly": [
                "temperature_2m",
                "precipitation",
                "wind_speed_10m",
                "relative_humidity_2m",
                "weather_code",
            ],
            "timezone": "auto",  # Let Open-Meteo determine based on lat/lon
        }
        try:
            responses = openmeteo.weather_api(api_url, params=params)
            response = responses[0]

            hourly = response.Hourly()
            # Create a dictionary for the DataFrame
            hourly_data_dict = {
                "date": pd.to_datetime(hourly.Time(), unit="s", utc=True)  # Timestamps
            }
            # Map variable names to DataFrame column names and get data
            variables_map = {
                "temperature_2m": "temperature_2m_celsius",
                "precipitation": "precipitation_mm",
                "wind_speed_10m": "wind_speed_10m_kmh",
                "relative_humidity_2m": "relative_humidity_2m_percent",
                "weather_code": "weather_code_wmo",
            }
            for i, var_name_in_api in enumerate(
                [
                    "temperature_2m",
                    "precipitation",
                    "wind_speed_10m",
                    "relative_humidity_2m",
                    "weather_code",
                ]
            ):
                df_col_name = variables_map.get(var_name_in_api, var_name_in_api)  # Use mapped name or original
                hourly_data_dict[df_col_name] = hourly.Variables(i).ValuesAsNumpy()

            hourly_df_for_day = pd.DataFrame(data=hourly_data_dict)
            all_hourly_weather_dfs.append(hourly_df_for_day)
            logging.info(f"Fetched {len(hourly_df_for_day)} hourly records for {ride_date_str}")

        except Exception as e:
            logging.warning(f"Failed to fetch or process weather for {ride_date_str}: {e}. Continuing to next date.")

    if not all_hourly_weather_dfs:
        logging.warning(f"No weather data successfully fetched for any ride day in {target_year}-{target_month:02d}.")
        return  # Or raise AirflowSkipException

    combined_weather_df = pd.concat(all_hourly_weather_dfs).reset_index(drop=True)

    combined_weather_df["year"] = target_year
    combined_weather_df["month"] = target_month  # The month of the DAG run / file

    output_dir = os.path.join(WAREHOUSE_BASE_PATH, f"year={target_year}", f"month={target_month:02d}")
    os.makedirs(output_dir, exist_ok=True)
    output_parquet_path = os.path.join(output_dir, "weather.parquet")

    logging.info(f"Writing {len(combined_weather_df)} total hourly weather rows to Parquet: {output_parquet_path}")
    try:
        combined_weather_df.to_parquet(output_parquet_path, index=False, engine="pyarrow")
    except Exception as e:
        logging.error(f"Error writing weather Parquet to {output_parquet_path}: {e}")
        raise

    logging.info(f"Successfully fetched and saved weather for specific ride days in {target_year}-{target_month:02d} into {output_parquet_path}")


# --- DAG Definition ---
with DAG(
    dag_id="daily_offline_ingest",  # Keep same DAG ID
    default_args=default_args,
    description="Ingest historical ride data and corresponding daily weather, one month per run.",
    schedule_interval="0 0 1 * *",  # Runs on the 1st of every month
    start_date=pendulum.datetime(2022, 1, 1, tz="UTC"),
    # Set catchup to False for easier development and testing with limited historical data
    # You can set to True when ready for a full backfill if you have all historical CSVs
    catchup=True,  # <-- change this
    max_active_runs=4,  # <-- add this (optional)
    tags=["ev-scooter", "ingestion", "batch", "rides", "weather"],
) as dag:
    ingest_monthly_rides_task = PythonOperator(
        task_id="ingest_ride_csv_to_parquet_for_month",
        python_callable=ingest_ride_data_for_month,
        op_kwargs={"logical_date_str": "{{ ds }}"},
    )

    fetch_weather_for_ride_days_task = PythonOperator(
        task_id="fetch_weather_for_ride_days",
        python_callable=fetch_weather_for_specific_ride_days,
        op_kwargs={"logical_date_str": "{{ ds }}"},
    )

    # Define dependencies: For this revised approach, they can run in parallel
    # as the weather task reads the CSV independently.
    # If you wanted to ensure rides are processed first for some other reason:
    # ingest_monthly_rides_task >> fetch_weather_for_ride_days_task
    # For now, let them be independent:
    # No explicit dependency means they can be scheduled in parallel by Airflow.
