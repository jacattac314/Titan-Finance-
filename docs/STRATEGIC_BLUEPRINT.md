# TitanFlow: Strategic Blueprint for an Institutional-Grade AI Trading Arena

## Executive Summary

TitanFlow is an architecturally ambitious project designed to be an
institutional-grade AI day trading system with "Glass Box" explainable AI.
The goal: 5–10 independent AI models compete in a virtual arena, executing
trades on real market data, with every decision fully traceable and explainable.

---

## Implementation Status

> Legend: ✅ Built | 🟡 Partial | ❌ Planned (not yet built)

| Component | Status | Notes |
|---|---|---|
| Event-driven microservice skeleton (gateway, signal, risk, execution) | ✅ | Full pub/sub pipeline wired |
| Virtual Portfolio Manager (VPM) | ✅ | `services/execution/core/portfolio.py` |
| `AlpacaDataProvider` | ✅ | Primary data source |
| `SyntheticDataProvider` | ✅ | Deterministic walk for dev/CI |
| LightGBM + SHAP strategy | ✅ | `lightgbm_strategy.py` |
| LSTM + Attention strategy / model | ✅ | `lstm_strategy.py`, `lstm_model.py` |
| TFT strategy / model | ✅ | `tft_strategy.py`, `tft_model.py` |
| SMA Crossover strategy | ✅ | `sma_crossover.py` |
| XAI / Explainability engine | ✅ | `services/signal/explainability.py` |
| Risk Guardian (kill switch, position sizing, Sharpe rollback) | ✅ | `services/risk/` |
| Order validator + slippage + latency simulation | ✅ | `services/execution/` |
| Trade audit logger | ✅ | `services/execution/audit.py` |
| CI pipeline (lint + pytest + docker build) | ✅ | `.github/workflows/ci.yml` |
| Next.js dashboard + Socket.IO | ✅ | `dashboard/` |
| `YahooFinanceProvider` fallback | ❌ | Planned — not yet built |
| PPO Reinforcement Learning model (Model 4) | ❌ | Planned — not yet built |
| RSI Mean-Reversion strategy (Model 5 baseline) | ❌ | Planned — not yet built |
| Meta-model stacking ensemble | ❌ | Planned — not yet built |
| Polygon / Binance data providers | ❌ | Planned — not yet built |
| Walk-forward validation harness | ❌ | Planned — not yet built |
| TimescaleDB persistence for arena state | ❌ | Planned — not yet built |
| Slack / email alerting | ❌ | Planned — not yet built |

---

## Architecture Vision

### Core Components

1. **Virtual Portfolio Manager (VPM)**
   - **Problem**: Alpaca Paper API limits to 1 account (or 3 distinct keys).
   - **Solution**: Custom internal ledger that simulates N unlimited portfolios.
   - **Role**: Tracks cash, positions, orders, and history per model.
     Routes validated orders to Alpaca for cross-validation but maintains
     internal truth.
   - **Status**: ✅ Built — `services/execution/core/portfolio.py`

2. **Data Ingestion Layer**
   - **Pattern**: Abstract base class (`DataProvider` in `providers/base.py`).
   - **Built**: `AlpacaDataProvider` (primary), `SyntheticDataProvider` (dev).
   - **Planned**: `YahooFinanceProvider` (fallback), Polygon, Binance.
   - **Distribution**: Redis Pub/Sub (`market_data` channel) for real-time fan-out.

3. **Model Arena (The "Glass Box")**
   - **Model 1**: LightGBM (Gradient Boosting) + SHAP TreeExplainer. ✅
   - **Model 2**: Temporal Fusion Transformer (TFT) + Variable Selection Network. ✅
   - **Model 3**: LSTM with Attention + Saliency Maps. ✅
   - **Model 4**: PPO Reinforcement Learning (FinRL). ❌ Planned
   - **Model 5**: Traditional Quant (RSI Mean Reversion / Momentum baseline). ❌ Planned
   - **Meta-Model**: Stacking Ensemble across all contenders. ❌ Planned

4. **Dashboard (Intelligence Layer)**
   - **Tech**: Next.js + TradingView Lightweight Charts + Recharts.
   - **Features**: Equity Curve Comparison, Live Leaderboard (Sortino, Calmar,
     Drawdown), "Why?" Button (Glass Box trace back to SHAP/attention values).
   - **Status**: ✅ Core dashboard built; "Why?" panel integration in progress.

---

## Implementation Roadmap

### Phase 1: Foundation (complete)

- [x] Alpaca API integration and key verification
- [x] Data abstraction layer (`DataProvider` ABC + Alpaca impl)
- [x] Virtual Portfolio Manager
- [x] Baseline strategies: SMA Crossover, LightGBM, LSTM, TFT
- [x] CI/CD pipeline (lint + pytest + docker build)
- [x] Risk → Execution pipeline wired end-to-end via `execution_requests`

### Phase 2: Arena Core (Weeks 3-4)

- [ ] Scale VPM for 5–10 concurrent model ledgers
- [ ] Order lifecycle states (NEW, PARTIAL, FILLED, REJECTED, CANCELLED)
- [ ] Real-time leaderboard metrics stream (Sortino, Calmar, Profit Factor)
- [ ] PPO / RSI Mean-Reversion contenders

### Phase 3: Dashboard & Glass Box (Weeks 5-6)

- [ ] TradingView equity curves per model
- [ ] "Why?" explainability panel (SHAP / attention values)
- [ ] Operational views (service health, stream lag, throughput)

### Phase 4: Production Hardening (Weeks 7-8)

- [ ] Persistent storage for arena state (TimescaleDB)
- [ ] Walk-forward validation harness
- [ ] Slack / email alerting
- [ ] Model registry + versioned contender config

---

## Technology Stack

| Layer | Technology | Status |
|---|---|---|
| Backend services | Python 3.10+, asyncio | ✅ |
| Frontend | Next.js, React, TailwindCSS | ✅ |
| Messaging | Redis Pub/Sub | ✅ |
| Time-series DB | QuestDB | ✅ |
| Relational DB | PostgreSQL | ✅ (schema only; full write paths in progress) |
| ML frameworks | PyTorch, LightGBM, scikit-learn | ✅ |
| Explainability | SHAP, attention saliency | ✅ |
| Containerisation | Docker & Docker Compose | ✅ |
| API backend | asyncio (no REST framework for streaming services) | ✅ |
