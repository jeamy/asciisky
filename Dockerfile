# syntax=docker/dockerfile:1.7
#
# Multi-stage image for asciisky (FastAPI + workers).
# Goals vs. previous single-stage build:
#   - no docker.io in the runtime image (app never calls Docker)
#   - no gcc/g++/cmake/make/python3-dev in runtime
#   - build tools only in the builder stage
#   - non-root runtime user
#   - smaller attack surface for Trivy image scans
#
# Build:
#   docker build -t asciisky-web:latest .
#   docker build -t asciisky-worker:latest .
#
# Note: same image is used for web + workers; CMD is overridden in compose.

ARG PYTHON_VERSION=3.14.7

# ---------------------------------------------------------------------------
# Stage 1: builder — compile/install Python deps into an isolated prefix
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build toolchain only here. Keep in sync with packages that may need
# compilation when wheels are missing (numpy/pandas/psutil/timezonefinder/…).
# libpq-dev: only needed if psycopg is built from source; psycopg[binary]
# usually ships wheels — still cheap insurance on new Python minors.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        make \
        cmake \
        python3-dev \
        libffi-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install into a relocatable prefix we can copy wholesale.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2: runtime — slim app image, no compilers, no docker CLI
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=Europe/Berlin

WORKDIR /app

# Runtime OS packages only:
#   tzdata  — Europe/Berlin
#   libffi8 — some cffi-backed wheels
#   libpq5  — only if a non-binary psycopg path is ever used; small
# Explicitly NOT installed: docker.io, gcc, g++, make, cmake, python3-dev
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
        libffi8 \
        libpq5 \
        openssl \
        libssl3t64 \
        openssl-provider-legacy \
        ca-certificates \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo "$TZ" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

# Python environment from builder
COPY --from=builder /opt/venv /opt/venv

# Application code (filtered by .dockerignore)
COPY --chown=appuser:appuser . .

# Ephemeris: do not download at build time. App uses local Loader('.') + bundled de421.bsp.

USER appuser

# Default: web. Workers override command in compose.
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
