# Operations Guide

## Requirements
*   Docker & Docker Compose
*   Python 3.10+ (for local development)
*   Node.js 18+ (for dashboard development)

## Environment Setup
Ensure a `.env` file exists in the root directory with the following keys:
```bash
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
REDIS_HOST=redis
POSTGRES_USER=titan
POSTGRES_PASSWORD=titan
POSTGRES_DB=titan_db
```

## Running the System
We use Docker Compose to orchestrate the entire stack.

### Start All Services
```bash
docker compose up -d --build
```

### View Logs
```bash
docker compose logs -f [service_name]
# Example:
docker compose logs -f signal
```

### Stop System
```bash
docker compose down
```

## Troubleshooting

### Dashboard `MODULE_NOT_FOUND` (socket.io/redis)
If the dashboard fails to start with "Cannot find module 'socket.io'", it often means the Docker build cache is stale or dependencies weren't copied correctly.
**Fix**:
```bash
docker compose build --no-cache dashboard
docker compose up -d dashboard
```

### Execution Service "Unauthorized"
If `execution` service logs show 401/Unauthorized errors from Alpaca:
1.  Check your `.env` file.
2.  Ensure `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are correct.
3.  Restart the service: `docker compose restart execution`.

### Redis Connection Refused
If services cannot connect to Redis:
1.  Ensure the `redis` container is running: `docker ps`.
2.  Check network connectivity in `docker-compose.yml` (all services should be on `titan_net`).
