# TitanFlow

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>
  <a href="https://www.python.org/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-blue.svg"></a>
  <a href="https://www.docker.com/"><img alt="Docker Compose" src="https://img.shields.io/badge/docker-compose-2496ED.svg?logo=docker&logoColor=white"></a>
  <a href=".github/workflows/ci.yml"><img alt="CI" src="https://github.com/jacattac314/Titan-Finance-/workflows/TitanFlow%20CI/badge.svg"></a>
</p>

## Overview

**TitanFlow** is an event-driven trading platform that separates market
ingestion, signal generation, risk controls, execution, and operator visibility
into independent, scalable services. Built with Python, Next.js, QuestDB, and
Redis, it provides real-time market data processing, AI-powered trading signals,
and a professional dashboard for traders.

### Key Features

- **Real-time Market Data Ingestion** — Alpaca IEX stream with tick persistence to QuestDB and Redis
- **AI Signal Generation** — Feature engineering + hybrid model inference (LSTM, TFT, LightGBM, SMA)
- **Glass Box Explainability** — Every signal includes SHAP feature-importance explanations
- **Risk Management Engine** — Kill-switch, fixed-fractional position sizing, rolling Sharpe / accuracy rollback
- **Paper Trading Arena** — Virtual portfolios with slippage and latency simulation; real-time leaderboard
- **Optional Live Trading** — Connect to Alpaca Trading API (paper mode default)
- **Professional Dashboard** — Next.js UI with real-time signal feed via Socket.IO

---

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Node.js 20+ (for dashboard development)
- Python 3.10+ (for service development)
- Alpaca API credentials (paper account recommended)

### Docker Deployment

```bash
git clone https://github.com/jacattac314/Titan-Finance-.git
cd Titan-Finance-

cp .env.example .env
# Edit .env: set ALPACA_API_KEY and ALPACA_SECRET_KEY

docker compose up --build -d
docker compose ps
docker compose logs -f gateway
```

### Run Dashboard Locally

```bash
cd dashboard
npm install
export REDIS_URL="redis://localhost:6379"
npm run dev
# Open http://localhost:3000
```

### Local Service Development

```bash
cd services/signal
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Architecture

### Repository Structure

| Directory | Purpose |
|---|---|
| `services/` | Core services: gateway, signal, risk, execution |
| `dashboard/` | Next.js operator UI + Socket.IO server |
| `docs/` | Architecture documentation and guides |
| `storage/schema/` | Database bootstrap and SQL schema |
| `scripts/` | Utility scripts (`sync_architecture.py`, etc.) |
| `tests/` | Test suite (unit + integration) |
| `legacy_frontend/` | Earlier Vite prototype (deprecated) |

### Runtime Topology

| Service | Container | Reads | Writes | Status |
|---|---|---|---|---|
| **gateway** | `titan_gateway` | Alpaca stream | QuestDB, `market_data` | ✅ |
| **signal** | `titan_signal` | `market_data` | `trade_signals` | ✅ |
| **risk** | `titan_risk` | `trade_signals`, `execution_filled` | `execution_requests`, `risk_commands` | ✅ |
| **execution** | `titan_execution` | `execution_requests`, `market_data`, `risk_commands` | `execution_filled`, `paper_portfolio_updates` | ✅ |
| **dashboard** | `titan_dashboard` | `execution_filled`, `paper_portfolio_updates`, `audit_events` | Browser UI | ✅ |

### Data Flow

```
Gateway → market_data → Signal → trade_signals → Risk → execution_requests → Execution
                                                    └── risk_commands ──────────────┘
                                                                     execution_filled ↩
```

### Exposed Ports

| Component | Port | Purpose |
|---|---|---|
| Dashboard (Next.js) | `3000` | Web UI |
| PostgreSQL | `5432` | Transactional data |
| Redis | `6379` | Pub/Sub messaging |
| QuestDB HTTP API | `9000` | API + web console |
| QuestDB ILP | `9009` | Influx line protocol ingestion |
| QuestDB PG Wire | `8812` | SQL access |

---

## Quality Assurance

### Running Tests

```bash
# Unit tests (from repo root)
pip install pytest pytest-asyncio
pytest tests/unit/ -v

# Dashboard quality checks
cd dashboard
npm run lint
npm run typecheck
npm run test
npm run build
```

### CI/CD Pipeline

Automated via GitHub Actions (`.github/workflows/ci.yml`):

- **Python lint** — flake8 syntax and undefined-name checks
- **Unit tests** — pytest across all services
- **Docker build** — validates all service images build cleanly
- **Docs sync** — `sync_architecture.py` runs on service code changes (`.github/workflows/docs-sync.yml`)

See [docs/TESTING.md](docs/TESTING.md) for full testing strategy.

---

## Documentation

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — System design, data flow, and service interactions
- **[STRATEGIC_BLUEPRINT.md](docs/STRATEGIC_BLUEPRINT.md)** — Vision, implementation status, and roadmap
- **[ROADMAP.md](ROADMAP.md)** — Phase-by-phase implementation plan
- **[OPERATIONS.md](docs/OPERATIONS.md)** — Troubleshooting and operational guides
- **[TESTING.md](docs/TESTING.md)** — Test strategies and commands
- **[dashboard/README.md](dashboard/README.md)** — Dashboard-specific setup

---

## Known Limitations

- Some environment variables in `.env.example` are forward-looking and not yet used
- PPO reinforcement learning, RSI mean-reversion, and stacking ensemble are planned but not yet implemented
- Service-level integration tests run connectivity checks only; full end-to-end scenario tests are in progress

---

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Security

For security issues, please see our [Security Policy](SECURITY.md). Do not open public issues for vulnerabilities.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Built with Python, Next.js, QuestDB, Redis &amp; Docker</strong>
</p>
