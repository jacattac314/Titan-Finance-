# TitanFlow Architecture

## System Overview
TitanFlow is an institutional-grade AI day trading system designed for high-frequency trading and real-time signal generation. It follows a microservices architecture, communicating primarily through asynchronous messaging (Redis Pub/Sub) to ensure low latency and high decoupling.

## Core Services

### 1. Market Data Gateway (`services/gateway`)
*   **Role**: Ingests real-time market data from infinite sources (e.g., Alpaca, Polygon, Binance).
*   **Tech Stack**: Python, FastAPI.
*   **Output**: Publishes normalized market ticks to Redis channel `market_data`.

### 2. Signal Engine (`services/signal`)
*   **Role**: Analyzes market data to generate trading signals.
*   **Logic**:
    *   Consumes `market_data`.
    *   Calculates technical indicators (RSI, MACD, Bollinger Bands) using `ta` library.
    *   Runs inference using pre-trained AI/ML models (e.g., PyTorch/TensorFlow).
*   **Output**: Publishes `trade_signals` (BUY/SELL + Confidence) to Redis.

### 3. Risk Guardian (`services/risk`)
*   **Role**: Validates signals against risk management rules.
*   **Checks**: Max drawdown, position limits, volatility checks.
*   **Output**: Forwards approved signals as `execution_requests` to Redis.

### 4. Trade Executor (`services/execution`)
*   **Role**: Executes trades with proper routing and order management.
*   **Integration**: Connects to Brokerage APIs (currently Alpaca).
*   **Output**: Publishes `execution_filled` events to Redis upon successful order submission/fill.

### 5. Dashboard (`dashboard`)
*   **Role**: Real-time user interface for monitoring and control.
*   **Tech Stack**: Next.js, Socket.IO, Recharts, TailwindCSS.
*   **Features**:
    *   Live Price Chart `PriceChart.tsx`.
    *   Signal Feed `SignalFeed.tsx`.
    *   Trade Log `TradeLog.tsx`.

## Data Infrastructure

### Redis
*   **Usage**: Message Bus (Pub/Sub) and Hot Cache.
*   **Channels**:
    *   `market_data`: Raw ticks.
    *   `trade_signals`: AI generated signals.
    *   `execution_requests`: Risk-approved orders.
    *   `execution_filled`: Confirmed trades.

### QuestDB
*   **Usage**: High-performance Time-series database for storing historical market data and signals for model retraining.

### PostgreSQL
*   **Usage**: Relational data (User profiles, configuration, long-term trade history).

## Data Flow
1.  **Ingestion**: Gateway receives tick -> Publishes to `market_data`.
2.  **Analysis**: Signal Service receives tick -> Calculates features -> Predicts -> Publishes `trade_signals`.
3.  **Validation**: Risk Service receives signal -> Checks limits -> Publishes `execution_requests`.
4.  **Execution**: Execution Service receives request -> Places order -> Publishes `execution_filled`.
5.  **Monitoring**: Dashboard executes real-time updates via WebSockets for all above events.
