# TitanFlow: Strategic Blueprint for an Institutional-Grade AI Trading Arena

## Executive Summary
TitanFlow is an architecturally ambitious project designed to be an institutional-grade AI day trading system with "Glass Box" explainable AI. The goal is to build a system where 5-10 independent AI models compete in a virtual arena, executing trades on real market data, with every decision fully traceable and explainable.

## Current State Analysis
*   **Repository**: `jacattac314/Titan-Finance-`
*   **Infrastructure**: Docker containerization is established (`build-and-test` -> `docker-build`).
*   **Data Source**: Alpaca Paper Trading API (registered Feb 15, 2026).
*   **Core Logic**: Early-stage scaffolding (Gateway, Execution, Signal services exist).

## Architecture Vision

### Core Components
1.  **Virtual Portfolio Manager (VPM)**:
    *   **Problem**: Alpaca Paper API limits to 1 account (or 3 distinct keys).
    *   **Solution**: A custom internal ledger that simulates N unlimited portfolios.
    *   **Role**: Tracks cash, positions, orders, and history for each model independently. Routes validated orders to Alpaca for "cross-validation" but maintains internal truth.

2.  **Data Ingestion Layer**:
    *   **Pattern**: Abstract Base Class (`DataProvider`).
    *   **Impls**: `AlpacaDataProvider` (primary), `YahooFinanceProvider` (fallback).
    *   **Distribution**: Redis Pub/Sub for real-time fan-out to all models.

3.  **Model Arena (The "Glass Box")**:
    *   **Model 1**: LightGBM (Gradient Boosting) + SHAP TreeExplainer.
    *   **Model 2**: Temporal Fusion Transformer (TFT) + Variable Selection Network.
    *   **Model 3**: LSTM with Attention + Saliency Maps.
    *   **Model 4**: PPO Reinforcement Learning (FinRL).
    *   **Model 5**: Traditional Quant (Mean Reversion/Momentum) for baseline.
    *   **Meta-Model**: Stacking Ensemble.

4.  **Dashboard (Intelligence Layer)**:
    *   **Tech**: React + TradingView Lightweight Charts + Recharts + Nivo.
    *   **Features**:
        *   Equity Curve Comparison.
        *   Live Leaderboard (Sortino, Calmar, Drawdown).
        *   "Why?" Button: Explains any trade execution (Glass Box).

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
*   [ ] **Alpaca API**: Verification and Key generation.
*   [ ] **Data Abstraction**: Implement `DataManager` with Alpaca/YFinance support.
*   [ ] **Virtual Portfolio**: Build `VirtualPortfolio` class for internal state tracking.
*   [ ] **Baselines**: Deploy SMA Crossover and RSI Mean Reversion models.
*   [ ] **CI/CD**: Fix current build failures.

### Phase 2: Multi-Model Engine (Weeks 3-4)
*   [ ] **Scale VPM**: Orchestrate 5-10 portfolios.
*   [ ] **Order Pipeline**: Validator -> Slippage Sim -> Fill Engine.
*   [ ] **Deploy Models**: Integrate LightGBM, TFT, LSTM, PPO.
*   [ ] **Metrics**: Compute Sortino, Calmar, Profit Factor real-time.

### Phase 3: Dashboard & Glass Box (Weeks 5-6)
*   [ ] **Real-Time Streaming**: FastAPI WebSocket backend.
*   [ ] **Visuals**: TradingView Charts for equity curves.
*   [ ] **Explainability**: Wire SHAP/Attention values to frontend "Why?" panel.

### Phase 4: Production Hardening (Weeks 7-8)
*   [ ] **Persistence**: Migrate to Postgres + TimescaleDB.
*   [ ] **Validation**: Walk-forward analysis and bootstrap testing.
*   [ ] **Regime Analysis**: Bull/Bear/Vol segmentation.
*   [ ] **Alerting**: Slack/Email integration.

## Technology Stack
*   **Language**: Python 3.10+ (Backend/ML), TypeScript (Frontend).
*   **Backend**: FastAPI.
*   **Frontend**: Next.js, React, TailwindCSS.
*   **Messaging**: Redis Pub/Sub.
*   **Database**: PostgreSQL (TimescaleDB extension planned).
*   **Containerization**: Docker & Docker Compose.
