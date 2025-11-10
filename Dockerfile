FROM python:3.13.3-slim

WORKDIR /app

# Install system dependencies and configure timezone
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    libpq-dev \
    tzdata \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Set timezone to Europe/Berlin (MESZ/CEST)
ENV TZ=Europe/Berlin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Do not download ephemeris data at build time. The app uses a local Loader('.') and a bundled de421.bsp.

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
