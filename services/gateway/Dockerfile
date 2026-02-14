FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (needed for some python packages like asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Default command (can be overridden by docker-compose)
CMD ["python", "main.py"]
