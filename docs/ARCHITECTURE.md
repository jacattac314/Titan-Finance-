# TitanFlow Architecture

> **Note**: Sections marked `<!-- AUTO:* -->` are regenerated automatically by
> `scripts/sync_architecture.py` whenever `services/**/*.py` files change.
> Edit the narrative prose freely — only the fenced blocks are overwritten.

## System Overview

TitanFlow is an institutional-grade AI day trading system designed for
high-frequency signal generation and paper/live order execution. It follows a
microservices architecture communicating through asynchronous Redis Pub/Sub
messaging to ensure low latency and high decoupling.

---

## Core Services

### 1. Market Data Gateway (`services/gateway`)

- **Role**: Ingests real-time market data and fans it out to all consumers.
- **Tech Stack**: Python 3.10, plain `asyncio` (no HTTP framework — long-lived
  streaming connections, no REST endpoints needed).
- **Providers**: Configurable via `DATA_PROVIDER` env var.
- **Output**: Publishes normalised market ticks to Redis channel `market_data`.
- **Storage**: Writes OHLCV ticks to QuestDB via UDP InfluxDB Line Protocol;
  also connects to PostgreSQL for metadata.

<!-- AUTO:providers:start -->
| Provider | File | Notes |
|---|---|---|
| `AlpacaDataProvider` | `services/gateway/providers/alpaca_provider.py` | Primary — live IEX stream |
| `SyntheticDataProvider` | `services/gateway/providers/synthetic_provider.py` | Deterministic random walk for local dev/CI |
<!-- AUTO:providers:end -->

---

### 2. Signal Engine (`services/signal`)

- **Role**: Analyses market data and generates trading signals.
- **Logic**:
  - Consumes `market_data`.
  - Calculates technical indicators (RSI, MACD, Bollinger Bands) via `ta`.
  - Runs inference across all registered strategy/model contenders.
- **Output**: Publishes `trade_signals` (BUY/SELL + confidence + SHAP
  explanation) to Redis.

<!-- AUTO:strategies:start -->
| Strategy | File | Model type |
|---|---|---|
| `LightGBMStrategy` | `services/signal/strategies/lightgbm_strategy.py` | Gradient boosting |
| `LSTMStrategy` | `services/signal/strategies/lstm_strategy.py` | Deep learning |
| `SMACrossover` | `services/signal/strategies/sma_crossover.py` | Rule-based |
| `TFTStrategy` | `services/signal/strategies/tft_strategy.py` | Transformer |
<!-- AUTO:strategies:end -->

<!-- AUTO:models:start -->
| Model class | File | Architecture |
|---|---|---|
| `LSTMModel` | `services/signal/models/lstm_model.py` | LSTM with attention |
| `TFTModel` | `services/signal/models/tft_model.py` | Temporal Fusion Transformer |
<!-- AUTO:models:end -->

---

### 3. Risk Guardian (`services/risk`)

- **Role**: Validates signals against risk management rules before forwarding
  to execution.
- **Checks**: Kill switch (max drawdown + consecutive losses), fixed-fractional
  position sizing, rolling Sharpe / accuracy thresholds, manual approval mode.
- **Output**:
  - Approved signals → `execution_requests` (consumed by Execution service).
  - Control commands → `risk_commands` (LIQUIDATE_ALL, ACTIVATE_MANUAL_APPROVAL).

---

### 4. Trade Executor (`services/execution`)

- **Role**: Executes risk-approved orders with realistic simulation or live
  Alpaca routing.
- **Modes**: `EXECUTION_MODE=paper` (default) or `EXECUTION_MODE=live`.
- **Subscriptions**: `execution_requests` (risk-approved orders), `market_data`
  (price cache), `risk_commands` (kill-switch / manual-approval commands).
- **Integration**: Connects to Alpaca paper/live API via `TitanAlpacaConnector`.
- **Output**: Publishes `execution_filled` events; paper mode also publishes
  `paper_portfolio_updates` (leaderboard snapshots).
- **Internal risk layer**: `OrderValidator` provides last-gate checks (position
  limits, order value caps) independent of the Risk service.

---

### 5. Dashboard (`dashboard`)

- **Role**: Real-time operator UI for monitoring and control.
- **Tech Stack**: Next.js, Socket.IO, Recharts, TailwindCSS.
- **Features**: Live Price Chart (`PriceChart.tsx`), Signal Feed
  (`SignalFeed.tsx`), Trade Log (`TradeLog.tsx`), Model Leaderboard.

---

## Data Infrastructure

### Redis

- **Usage**: Message bus (Pub/Sub) and hot cache.

<!-- AUTO:channels:start -->
| Channel | Publisher(s) | Subscriber(s) | Payload |
|---|---|---|---|
| `audit_events` | execution | — | audit trail record |
| `execution_filled` | execution | risk | fill event |
| `execution_requests` | risk | execution | risk-approved order (qty, side, model_id) |
| `market_data` | gateway | execution, signal | normalised tick |
| `paper_portfolio_updates` | execution | — | leaderboard snapshot |
| `risk_commands` | risk | execution | LIQUIDATE_ALL / ACTIVATE_MANUAL_APPROVAL |
| `trade_signals` | signal | risk | BUY/SELL + confidence + explanation |
<!-- AUTO:channels:end -->

### QuestDB

- **Usage**: High-performance time-series store for OHLCV ticks; feeds signal
  feature engineering and model retraining.

### PostgreSQL

- **Usage**: Relational data — configuration, long-term trade history, user
  metadata.

---

## Data Flow

```
┌─────────┐  market_data   ┌────────┐  trade_signals  ┌──────┐  execution_requests  ┌───────────┐
│ Gateway │ ─────────────► │ Signal │ ───────────────► │ Risk │ ───────────────────► │ Execution │
└─────────┘                └────────┘                  └──────┘                      └───────────┘
                                                           │  risk_commands                │
                                                           └──────────────────────────────►│
                                                                                           │
                                                                              execution_filled
                                                                           ◄───────────────┘
                                                        (Risk reads execution_filled for
                                                         rolling Sharpe / accuracy tracking)

Dashboard subscribes to: execution_filled, paper_portfolio_updates, audit_events
```

1. **Ingestion**: Gateway receives tick → publishes to `market_data`.
2. **Analysis**: Signal service receives tick → calculates features → runs
   all strategy contenders → publishes `trade_signals`.
3. **Validation**: Risk service receives signal → checks limits + kill switch
   → publishes `execution_requests` (approved) or drops signal (rejected).
4. **Execution**: Execution service receives request → applies slippage /
   latency simulation → places order → publishes `execution_filled`.
5. **Feedback**: Risk reads `execution_filled` to update rolling Sharpe /
   accuracy and trigger model rollback if thresholds are breached.
6. **Monitoring**: Dashboard streams all events via Socket.IO WebSockets.

---

## Known Limitations / Planned Work

- PPO Reinforcement Learning model — planned, not yet implemented.
- YahooFinance fallback data provider — planned, not yet implemented.
- Meta-model stacking ensemble — planned, not yet implemented.
- RSI Mean-Reversion strategy — planned, not yet implemented.
- Polygon and Binance data providers — planned, not yet implemented.
- PostgreSQL write paths (beyond schema init) not fully wired in all services.

---

*Last auto-synced: see git log on this file.*
