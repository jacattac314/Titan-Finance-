# TitanFlow

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>a>
    <a href="https://www.python.org/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-blue.svg"></a>a>
      <a href="https://www.docker.com/"><img alt="Docker Compose" src="https://img.shields.io/badge/docker-compose-2496ED.svg?logo=docker&logoColor=white"></a>a>
        <a href=".github/workflows/ci.yml"><img alt="CI/CD" src="https://github.com/jacattac314/Titan-Finance-/workflows/CI/CD/badge.svg"></a>a>
</p>

## Overview

**TitanFlow** is an event-driven trading platform that separates market ingestion, signal generation, risk controls, execution, and operator visibility into independent, scalable services. Built with modern technologies (Python, Next.js, QuestDB, Redis), it provides real-time market data processing, AI-powered trading signals, and a professional dashboard for traders.

### Key Features

- **Real-time Market Data Ingestion** – Alpaca (IEX stream) with tick persistence to QuestDB and Redis
- - **AI Signal Generation** – Feature engineering + hybrid model inference for intelligent trading decisions
  - - **Multi-Model Signal Stream** – Hybrid AI, SMA crossover, and RSI mean-reversion strategies
    - - **Risk Management Engine** – Kill-switch logic and position sizing utilities
      - - **Paper Trading Arena** – Backtest strategies with fake cash and real market prices
        - - **Live Model Leaderboard** – Track and compare strategy performance
          - - **Optional Live Trading** – Connect to Alpaca Trading API for real execution (paper mode default)
            - - **Professional Dashboard** – Next.js UI with real-time signal feed via Socket.IO
             
              - ## Quick Start
             
              - ### Prerequisites
             
              - - Docker Desktop (or Docker Engine + Compose)
                - - Node.js 20+ (for dashboard development)
                  - - Python 3.10+ (for service development)
                    - - Alpaca API credentials (paper account recommended)
                     
                      - ### Docker Deployment
                     
                      - ```bash
                        # Clone the repository
                        git clone https://github.com/jacattac314/Titan-Finance-.git
                        cd Titan-Finance-

                        # Copy environment template
                        cp .env.example .env

                        # Set required secrets
                        # - ALPACA_API_KEY
                        # - ALPACA_SECRET_KEY

                        # Build and start all services
                        docker compose up --build -d

                        # Verify container health
                        docker compose ps
                        docker compose logs -f gateway
                        ```

                        ### Run Dashboard Locally

                        The dashboard includes a custom Node server for Socket.IO integration.

                        ```bash
                        cd dashboard
                        npm install

                        # Set Redis URL (if running outside Docker network)
                        export REDIS_URL="redis://localhost:6379"

                        # Start development server
                        npm run dev

                        # Open http://localhost:3000
                        ```

                        ### Local Service Development

                        ```bash
                        cd services/signal
                        python -m venv .venv
                        source .venv/bin/activate  # On Windows: .venv\Scripts\activate
                        pip install -r requirements.txt
                        python main.py
                        ```

                        ## Architecture

                        ### Repository Structure

                        | Directory | Purpose |
                        |-----------|---------|
                        | `services/` | Core services: gateway, signal, risk, execution |
                        | `dashboard/` | Next.js operator UI + Socket.IO server |
                        | `docs/` | Architecture documentation and guides |
                        | `storage/schema/` | Database bootstrap and SQL schema |
                        | `scripts/` | Utility scripts for setup and operations |
                        | `tests/` | Test suite for services and components |
                        | `legacy_frontend/` | Earlier Vite prototype (deprecated) |

                        ### Runtime Topology

                        | Service | Container | Dependencies | Reads | Writes | Status |
                        |---------|-----------|--------------|-------|--------|--------|
                        | **gateway** | `titan_gateway` | Postgres, QuestDB, Redis | Alpaca stream | QuestDB, Redis | ✅ Implemented |
                        | **signal** | `titan_signal` | QuestDB, Redis | QuestDB bars | Redis | ✅ Implemented |
                        | **risk** | `titan_risk` | Redis | Config/env | In-memory | 🟡 Partial |
                        | **execution** | `titan_execution` | Redis | Trade signals, market data | Execution events | ✅ Implemented |
                        | **dashboard** | Local process | Redis (optional) | Redis channels | Browser UI | ✅ Implemented |

                        ### Exposed Ports

                        | Component | Port | Purpose |
                        |-----------|------|---------|
                        | Dashboard (Next.js) | `3000` | Web UI |
                        | PostgreSQL | `5432` | Transactional data |
                        | Redis | `6379` | Pub/Sub messaging |
                        | QuestDB HTTP API | `9000` | API + web console |
                        | QuestDB ILP | `9009` | Influx line protocol ingestion |
                        | QuestDB PG Wire | `8812` | SQL access |

                        ## Quality Assurance

                        ### Local Testing

                        ```bash
                        # Backend service testing
                        cd services/signal
                        python -m venv .venv
                        source .venv/bin/activate
                        pip install -r requirements.txt
                        python -m pytest

                        # Dashboard quality checks
                        cd dashboard
                        npm run lint      # ESLint
                        npm run typecheck # TypeScript
                        npm run test      # Jest
                        npm run build     # Production build
                        ```

                        ### CI/CD Pipeline

                        The repository includes automated CI/CD via GitHub Actions (`.github/workflows/ci.yml`):

                        - **Python Lint** – flake8 code quality checks
                        - - **Docker Build** – Validates all service images
                          - - **Type Safety** – TypeScript checks for dashboard
                            - - **Integration Tests** – Service-level validation (in progress)
                             
                              - See [docs/TESTING.md](docs/TESTING.md) for detailed testing strategies.
                             
                              - ## Documentation
                             
                              - - **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** – System design, data flow, and service interactions
                                - - **[ROADMAP.md](ROADMAP.md)** – Implementation timeline and planned features
                                  - - **[ENVIRONMENT.md](docs/ENVIRONMENT.md)** – Complete environment variable reference
                                    - - **[OPERATIONS.md](docs/OPERATIONS.md)** – Troubleshooting and operational guides
                                      - - **[TESTING.md](docs/TESTING.md)** – Test strategies and commands
                                        - - **[dashboard/README.md](dashboard/README.md)** – Dashboard-specific setup and development
                                         
                                          - ## Known Limitations
                                         
                                          - - Risk and execution services do not yet consume Redis channels end-to-end
                                            - - Some environment variables in `.env.example` are forward-looking and not yet used
                                              - - Service-level integration tests are not yet enforced in CI
                                               
                                                - ## Contributing
                                               
                                                - We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
                                               
                                                - ### Code of Conduct
                                               
                                                - This project adheres to the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold these standards.
                                               
                                                - ## Security
                                               
                                                - For security issues, please see our [Security Policy](SECURITY.md). Do not open public issues for vulnerabilities.
                                               
                                                - ## License
                                               
                                                - This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
                                               
                                                - ---

                                                <p align="center">
                                                  <strong>Built with Python, Next.js, QuestDB, Redis & Docker</strong>strong>
                                                </p>p></strong>
