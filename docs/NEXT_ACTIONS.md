# Immediate Next Actions

This is the recommended execution order for the next development cycle.

## 1) Close the risk-gating gap first (P0)
- Make `execution` consume only `execution_requests` for order execution in paper mode.
- Prevent raw `trade_signals` from generating fills directly.
- Add an explicit regression test proving that only risk-approved events can execute.

**Why now:** This is the highest-impact architecture correctness issue and directly affects MVP credibility.

## 2) Add one deterministic end-to-end contract test (P0)
- Validate the full chain:
  `market_data` -> `trade_signals` -> `execution_requests` -> `execution_filled`.
- Assert required payload fields at each hop.
- Fail fast when a channel name or contract drifts.

**Why now:** It prevents silent breakages in service-to-service messaging.

## 3) Introduce shared event schemas (P1)
- Create shared models for:
  - `MarketDataEvent`
  - `TradeSignalEvent`
  - `ExecutionRequestEvent`
  - `ExecutionFilledEvent`
- Require validation at producer and consumer boundaries.
- Include a schema version in each event.

**Why now:** Schema discipline is the next reliability bottleneck after channel wiring.

## 4) Harden demo operations (P1)
- Add `/healthz` and `/readyz` per service (or equivalent heartbeat checks).
- Add one command/script to verify all services are ready before demo flow.
- Surface backend connectivity status in the dashboard.

**Why now:** It reduces demo risk and shortens troubleshooting time.

## Suggested first ticket
**Title:** Make execution consume `execution_requests` and add regression test for risk-gated trade flow.

**Done criteria:**
- Raw `trade_signals` alone never produce `execution_filled`.
- Risk-approved `execution_requests` do produce fills.
- The contract test fails if any required channel hop breaks.
