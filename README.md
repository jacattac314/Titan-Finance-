# TitanFlow

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)

TitanFlow is an event-driven trading platform that separates market ingestion, signal generation, risk controls, execution, and operator visibility into independent services.

## Overview

TitanFlow currently includes:
- Real-time market tick ingestion from Alpaca (IEX stream).
- Tick persistence to QuestDB and Redis fan-out for downstream consumers.
- AI signal generation using feature engineering + hybrid model inference.
- Multi-model signal stream (Hybrid AI + baseline SMA crossover + RSI mean-reversion).
- Risk engine scaffolding with kill-switch logic and position sizing utilities.
- Paper-trading arena with fake cash, real market prices, and live model leaderboard.
- Optional live execution mode connected to Alpaca Trading API.
- Next.js dashboard with live signal feed support via Socket.IO.

## Repository Layout

| Area | Purpose | Path |
| :--- | :--- | :--- |
| Core services | Gateway, signal, risk, and execution workers | `services/` |
| Dashboard | Operator UI + Socket.IO bridge server | `dashboard/` |
| Database bootstrap | SQL schema/init scripts | `storage/schema/` |
| Architecture docs | System design and data flow notes | `docs/ARCHITECTURE.md` |
| Legacy frontend demo | Earlier Vite prototype | `legacy_frontend/` |

## Runtime Topology

| Service | Container | Depends On | Reads | Writes | Implementation Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `gateway` | `titan_gateway` | Postgres, QuestDB, Redis | Alpaca market stream | QuestDB `market_data`, Redis `market_data` | Implemented |
| `signal` | `titan_signal` | QuestDB, Redis | QuestDB bars | Redis `trade_signals` | Implemented |
| `risk` | `titan_risk` | Redis | Config/env | In-memory decisions only | Partial (Redis I/O TODO) |
| `execution` | `titan_execution` | Redis | `trade_signals`, `market_data` | `execution_filled`, `paper_portfolio_updates` | Implemented (paper mode default, live optional) |
| `dashboard` | local process | Redis (optional) | Redis `trade_signals` via server bridge | Browser UI updates | Implemented |

## Exposed Ports

| Component | Port(s) | Purpose |
| :--- | :--- | :--- |
| Dashboard (Next.js) | `3000` | Web UI |
| PostgreSQL | `5432` | Transactional data |
| Redis | `6379` | Pub/Sub messaging |
| QuestDB HTTP | `9000` | API + web console |
| QuestDB ILP | `9009` | Influx line protocol ingest |
| QuestDB PG Wire | `8812` | SQL access |

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Node.js 20+ (dashboard development)
- Python 3.10+ (service development)
- Alpaca API credentials (paper account recommended)

## Quick Start (Docker)

1. Clone the repository.

```bash
git clone https://github.com/jacattac314/Titan-Finance-.git
cd Titan-Finance-
```

2. Create `.env` from the template.

```bash
# bash/zsh
cp .env.example .env

# powershell
Copy-Item .env.example .env
```

3. Set required secrets in `.env`:
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`

4. Build and start the platform.

```bash
docker compose up --build -d
```

5. Verify container health.

```bash
docker compose ps
docker compose logs -f gateway
```

## Run Dashboard Locally

The dashboard app lives in `dashboard/` and includes a custom Node server (`server.js`) for Socket.IO.

```bash
cd dashboard
npm install
```

Set Redis URL if running outside Docker network.

```powershell
$env:REDIS_URL="redis://localhost:6379"
```

Run development server:

```bash
npm run dev
```

Open `http://localhost:3000`.

## Local Development Workflows

### Backend service only

```bash
cd services/signal
python -m venv .venv
# activate venv
pip install -r requirements.txt
python main.py
```

### Dashboard quality checks

```bash
cd dashboard
npm run lint
npm run typecheck
npm run test
npm run build
```

## Validation and CI

- CI workflow: `.github/workflows/ci.yml`
- Current CI stages:
  - Python lint (`flake8`)
  - Docker image build (`docker compose build`)

For local test guidance, see `docs/TESTING.md`.

## Documentation Index

- System design: `docs/ARCHITECTURE.md`
- Environment variables: `docs/ENVIRONMENT.md`
- Operations and troubleshooting: `docs/OPERATIONS.md`
- Test strategy and commands: `docs/TESTING.md`
- Contribution process: `CONTRIBUTING.md`
- Dashboard specifics: `dashboard/README.md`

## Known Gaps

- `risk` and `execution` services do not yet consume Redis channels end-to-end.
- Some environment variables in `.env.example` are forward-looking and not yet used at runtime.
- CI currently emphasizes Python lint + Docker build; service-level integration tests are not yet enforced.

## Contributing

Please read `CONTRIBUTING.md` before opening a PR.

## License

MIT. See `LICENSE`.
