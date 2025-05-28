#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

AIRFLOW_USER=${AIRFLOW_USER:-airflow}
AIRFLOW_PASSWORD=${AIRFLOW_PASSWORD:-airflow}
AIRFLOW_EMAIL=${AIRFLOW_EMAIL:-airflow@example.com}

# Wait for Postgres to be ready using the 'postgres' service name from docker-compose
echo "Waiting for postgres..."
# The 'postgres' service is the one defined in your docker-compose.yml
# The '5432' is the internal port of the postgres container
while ! nc -z postgres 5432; do
  sleep 1
done
echo "Postgres is up - continuing..."

# Initialize Airflow metadata database (if not already initialized)
# Note: We use a separate DB for Airflow metadata, specified by AIRFLOW_DB_NAME
echo "Initializing Airflow database: ${AIRFLOW_DB_NAME}"
airflow db init

# Create Airflow admin user (if it doesn't exist)
airflow users create \
    --username "${AIRFLOW_USER}" \
    --password "${AIRFLOW_PASSWORD}" \
    --firstname Airflow \
    --lastname Admin \
    --role Admin \
    --email "${AIRFLOW_EMAIL}" \
    || true # Don't fail if user already exists

# Start the Airflow component passed as an argument (webserver, scheduler)
exec airflow "$@"