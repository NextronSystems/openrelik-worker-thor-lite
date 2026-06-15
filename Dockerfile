# Use the official Docker Hub Ubuntu base image
FROM ubuntu:24.04

LABEL org.opencontainers.image.version="2026.02.27"
LABEL org.opencontainers.image.title="OpenRelik Worker for THOR Lite"
LABEL org.opencontainers.image.source="https://github.com/NextronSystems/openrelik-worker-thor-lite"

# Prevent needing to configure debian packages, stopping the setup of
# the docker container.
RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Install poetry and any other dependency that your worker needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    sudo \
    fdisk \
    qemu-utils \
    ntfs-3g \
    ewf-tools \
    btrfs-progs \
    unzip \
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

# Configure debugging
ARG OPENRELIK_PYDEBUG
ENV OPENRELIK_PYDEBUG=${OPENRELIK_PYDEBUG:-0}
ARG OPENRELIK_PYDEBUG_PORT
ENV OPENRELIK_PYDEBUG_PORT=${OPENRELIK_PYDEBUG_PORT:-5678}

# Set working directory
WORKDIR /openrelik

# Install the latest uv binaries
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy poetry toml and install dependencies
COPY uv.lock pyproject.toml .

# Install the project's dependencies using the lockfile and settings
RUN uv sync --locked --no-install-project --no-dev

# Copy project files
COPY . ./

# Installing separately from its dependencies allows optimal layer caching
RUN uv sync --locked --no-dev

# Install the worker and set environment to use the correct python interpreter.
ENV PATH="/openrelik/.venv/bin:$PATH"

# Default command if not run from docker-compose (and command being overidden)
CMD ["celery", "--app=src.tasks", "worker", "--task-events", "--concurrency=1", "--loglevel=DEBUG"]
