# TitanFlow MVP: What Must Happen Next

## Goal
Ship a **working MVP** that can be demoed end-to-end in paper mode:

1. Gateway emits market data.
2. Signal service emits at least one deterministic strategy signal.
3. Risk service approves/rejects and forwards requests.
4. Execution service executes only approved requests.
5. Dashboard shows signals, fills, and model leaderboard updates.

---

## Current State (from codebase)

### What already works
- All core services exist and are wired in Docker Compose (`gateway`, `signal`, `risk`, `execution`, `dashboard`, plus Redis/Postgres/QuestDB). 
- Unit test suite is healthy (`110 passed`).
- Paper execution publishes `execution_filled` and `paper_portfolio_updates`, which the dashboard already consumes.

### MVP blockers

#### 1) Risk is currently bypassed by execution channel mismatch (**P0**)
- `risk` publishes approved orders to `execution_requests`.
- `execution` subscribes to `trade_signals` (not `execution_requests`) in both live and paper modes.
- Result: execution can run directly off raw signals, which breaks the intended risk-gated pipeline.

**Why this blocks MVP:** You cannot claim a working risk-validated pipeline if execution ignores risk output.

#### 2) No deterministic end-to-end integration test of the full pipeline (**P0**)
- Existing integration script validates Redis connectivity shape, but does not enforce full contract behavior (signal -> risk -> execution).
- MVP needs one automated test that fails if channel contracts break.

**Why this blocks MVP:** Without one contract/integration test, regressions in cross-service messaging are likely and hard to detect.

#### 3) No schema contract shared across services (**P1**)
- Signal, risk, execution each build payloads ad hoc (dictionary literals in each service).
- No central schema/versioning for required fields, enum values, or optional metadata.

**Why this matters now:** It is the next reliability bottleneck after channel wiring.

#### 4) Ops readiness is partial (health/readiness, startup assertions) (**P1**)
- Services rely on startup logs and Redis ping but do not expose health/readiness endpoints.
- Compose `depends_on` only partially protects runtime correctness.

**Why this matters now:** Demo reliability and faster diagnosis of startup failures.

---

## Recommended MVP Plan (ordered)

## Step 1 — Enforce risk-gated execution path (P0)
**Deliverable:** `execution` consumes `execution_requests` as its trade input channel in paper mode (and optionally live mode, if live should stay risk-gated).

**Acceptance criteria:**
- A raw `trade_signals` message does not trigger a fill unless risk forwards it.
- A valid risk-approved payload on `execution_requests` produces `execution_filled`.
- Dashboard still updates correctly from `execution_filled` + `paper_portfolio_updates`.

## Step 2 — Add one deterministic end-to-end contract test (P0)
**Deliverable:** Integration test (or docker-compose smoke test script) that validates the channel chain:
`market_data` -> `trade_signals` -> `execution_requests` -> `execution_filled`.

**Acceptance criteria:**
- Test fails if any hop is missing.
- Test validates required payload keys at each hop.
- Test runs in CI (or at minimum as a required local pre-release check).

## Step 3 — Introduce shared event schemas (P1)
**Deliverable:** Shared Pydantic models / dataclasses for:
- `MarketDataEvent`
- `TradeSignalEvent`
- `ExecutionRequestEvent`
- `ExecutionFilledEvent`

**Acceptance criteria:**
- Producers validate before publish.
- Consumers validate on read (with structured logging on schema failure).
- Schema version included in messages.

## Step 4 — Add health/readiness endpoints + runbook checks (P1)
**Deliverable:** Lightweight `/healthz` and `/readyz` endpoints per service (or equivalent heartbeat channel).

**Acceptance criteria:**
- Can confirm all service readiness in <10s with one script.
- Dashboard displays backend connectivity summary.

---

## Definition of “Working MVP” (exit checklist)
- [ ] In paper mode, a full trade loop is visible in dashboard within a single run.
- [ ] Risk gates every execution (no direct signal-to-execution bypass).
- [ ] One deterministic integration test verifies the full message flow.
- [ ] Event schemas are validated at service boundaries.
- [ ] A simple ops check confirms service health/readiness.

---

## Suggested first implementation ticket
**Ticket:** “Make execution consume `execution_requests` and add regression test for risk-gated trade flow.”

This single ticket removes the largest architecture gap and converts current components into an MVP-grade pipeline.
