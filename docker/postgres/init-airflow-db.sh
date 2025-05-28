#!/bin/bash
set -e

# This script will be executed when the Postgres container starts for the first time.
# It creates the database specified by the AIRFLOW_DB_NAME environment variable
# if it doesn't already exist.
# The main database (POSTGRES_DB) is created automatically by the postgres image.
# We need to explicitly create the one for Airflow.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${AIRFLOW_DB_NAME}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${AIRFLOW_DB_NAME}')\gexec
EOSQL