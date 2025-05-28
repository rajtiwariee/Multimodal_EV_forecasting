# Start from the official Apache Airflow image, matching your current version
ARG AIRFLOW_VERSION=2.7.3
FROM apache/airflow:${AIRFLOW_VERSION}

# Label to identify your custom image (optional)
LABEL maintainer="your-email@example.com"
LABEL description="Custom Airflow image with project-specific Python dependencies."

# Argument to define the Python version, can be useful if base image supports multiple
# For apache/airflow:2.7.3, it's Python 3.8. Check the base image tags if you need other versions.
ARG PYTHON_VERSION=3.8

USER root
# Example: Install system-level dependencies if any of your Python packages need them
# For instance, if a package needed 'gcc' or 'libpq-dev'
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     # Add system packages here, e.g., libpq-dev gcc \
#  && apt-get clean \
#  && rm -rf /var/lib/apt/lists/*
# For openmeteo_requests, requests-cache, retry-requests, pandas, pyarrow, no specific system deps are usually needed beyond what's in the base image.

USER airflow

# Copy the project's requirements.txt to a temporary location in the image
# This requirements.txt should be the one at the root of your project.
# The Docker build context will be set to ./docker/airflow, so we need to go up.
COPY ../../requirements.txt /requirements.txt

# Install Python dependencies from the requirements.txt file
# Using --user can sometimes cause issues with PATH, let's try a system-wide pip install for the airflow user.
# To do this robustly, switch to root, install, then switch back, or ensure airflow user has write permissions.
# The base airflow image's pip should be configured correctly.
# Let's try pip install as the airflow user directly.
# If this fails due to permissions, we might need to adjust.
RUN pip install --no-cache-dir -r /requirements.txt

# You can add more RUN commands here if needed, e.g., to copy custom scripts or set environment variables
# Note: Your existing entrypoint script in docker-compose.yml will still be used.
# This Dockerfile is just for preparing the image with dependencies.