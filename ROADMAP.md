# TitanFlow Roadmap

This roadmap is the implementation plan for turning TitanFlow into a production-grade AI trading arena.

## Current Status (February 2026)
- Done: event-driven service skeleton (`gateway`, `signal`, `risk`, `execution`).
- Done: paper-trading mode with virtual portfolio leaderboard.
- Done: baseline strategy contenders (`SMA Crossover`, `RSI Mean Reversion`) plus `Hybrid AI` contender.
- In progress: execution/risk integration hardening and model package organization.
- In progress: dashboard polish and deployment paths (GitHub Pages prototype + Next.js ops dashboard).

## Phase 1: Foundation Stabilization (Week 1-2)
- Finalize data provider abstraction and fallback provider behavior.
- Harden `risk -> execution` pipeline contract (payload schema, retries, idempotency).
- Enforce typed signal schema across services (`model_id`, confidence, explanation format).
- Add service health endpoints + startup readiness checks.
- Exit criteria: end-to-end paper trade loop is deterministic and test-covered.
- Exit criteria: all core services run cleanly via `docker compose up --build`.

## Phase 2: Arena Core (Week 3-4)
- Expand Virtual Portfolio Manager for 5-10 concurrent model ledgers.
- Add realistic fill simulation controls (slippage, latency, partial fills).
- Add order lifecycle states (`NEW`, `PARTIAL`, `FILLED`, `REJECTED`, `CANCELLED`).
- Implement portfolio/risk limits per contender.
- Publish unified leaderboard metrics stream (PnL, win rate, drawdown, turnover).
- Exit criteria: arena can run continuously on real-time data without ledger drift.
- Exit criteria: metrics are stable and auditable per model.

## Phase 3: Model Expansion (Week 5-6)
- Add model registry and model loading contracts.
- Integrate additional contenders (LightGBM, TFT/LSTM variant, RL baseline).
- Standardize explainability payloads (top features, confidence decomposition).
- Add walk-forward validation harness and baseline comparison suite.
- Exit criteria: at least 5 contenders active with comparable metrics.
- Exit criteria: every trade can be traced back to model decision artifacts.

## Phase 4: Dashboard Intelligence (Week 7-8)
- Add leaderboard drill-down pages (model equity, drawdown, trade distribution).
- Add “Why this trade?” explainability view with per-trade context.
- Add operational views (service health, stream lag, order throughput).
- Add role-ready presentation mode for stakeholders.
- Exit criteria: dashboard supports both operator monitoring and investor/demo storytelling.

## Phase 5: Production Hardening (Week 9-10)
- Add persistent storage for arena state snapshots and trade history.
- Add regression suites for feature engineering and signal output.
- Add alerting hooks (Slack/email/webhooks) for risk and service incidents.
- Add release/versioning process for model bundles.
- Exit criteria: reproducible runs, rollback path, and incident response playbook in place.

## Immediate Next Milestones
- M1: Lock payload schemas and add contract tests.
- M2: Complete risk-execution bridge and kill-switch behavior.
- M3: Add slippage/latency simulator in execution.
- M4: Promote model registry + contender config from code to env/config files.

## Tracking Notes
- This roadmap is intentionally execution-focused and should be updated as milestones close.
- For architecture context, see `docs/ARCHITECTURE.md`.
- For strategic context, see `docs/STRATEGIC_BLUEPRINT.md`.

