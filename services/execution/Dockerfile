FROM python:3.10-slim

WORKDIR /app

COPY services/execution/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared/schemas.py schemas.py
COPY shared/health.py health.py

COPY services/execution/ .

CMD ["python", "main.py"]
