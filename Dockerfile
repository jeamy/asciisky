FROM python:3.9-slim

WORKDIR /app

# Install system dependencies and configure timezone
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone to Europe/Berlin (MESZ/CEST)
ENV TZ=Europe/Berlin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir numpy==1.23.5 && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Download ephemeris data
RUN python -c "from skyfield.api import load; load('de421.bsp')"

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
