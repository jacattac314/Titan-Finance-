FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (needed for some python packages like asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared/schemas.py schemas.py
COPY shared/health.py health.py

# Copy service source code
COPY services/gateway/ .

# Default command (can be overridden by docker-compose)
CMD ["python", "main.py"]
