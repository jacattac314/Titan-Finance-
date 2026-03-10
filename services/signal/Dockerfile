FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/signal/requirements.txt .
# Install PyTorch CPU version for smaller image size in dev
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared/schemas.py schemas.py
COPY shared/health.py health.py

COPY services/signal/ .

CMD ["python", "main.py"]
