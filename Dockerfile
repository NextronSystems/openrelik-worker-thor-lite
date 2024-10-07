# Use the official Docker Hub Ubuntu base image
FROM ubuntu:24.04

LABEL org.opencontainers.image.version="2024.10.07"
LABEL org.opencontainers.image.title="OpenRelik Worker for THOR Lite"
LABEL org.opencontainers.image.source="https://github.com/NextronSystems/openrelik-worker-thor-lite"

# Prevent needing to configure debian packages, stopping the setup of
# the docker container.
RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Install poetry and any other dependency that your worker needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-poetry \
    curl \
    unzip \
    # Add your dependencies here
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------
# Install THOR Lite
# ----------------------------------------------------------------------
WORKDIR /thor-lite
RUN curl -o thorlite-linux.zip "https://update1.nextron-systems.com/getupdate.php?product=thor10lite-linux&dev=1" \
    && unzip thorlite-linux.zip \
    && rm thorlite-linux.zip \
    && chmod +x thor-lite-linux-64
# ----------------------------------------------------------------------

# Configure poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Set working directory
WORKDIR /openrelik

# Copy files needed to build
COPY . ./

# Install the worker and set environment to use the correct python interpreter.
RUN poetry install && rm -rf $POETRY_CACHE_DIR
ENV VIRTUAL_ENV=/app/.venv PATH="/openrelik/.venv/bin:$PATH"

# Default command if not run from docker-compose (and command being overidden)
CMD ["celery", "--app=src.tasks", "worker", "--task-events", "--concurrency=1", "--loglevel=INFO"]
