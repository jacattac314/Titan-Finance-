# Test Coverage Analysis

> **Status**: This document was written as a gap analysis before unit tests were
> added to the repository. The findings drove the test implementation that now
> lives in `tests/unit/`. The original analysis is preserved below as a
> historical record; current coverage state is tracked by `pytest-cov` in CI.

---

## Current Coverage (as of February 2026)

18 unit test files exist in `tests/unit/`, covering all five core service areas:

| Test file | Service area |
|---|---|
| `test_risk_engine.py` | `services/risk/` |
| `test_portfolio.py` | `services/execution/core/` |
| `test_virtual_portfolio.py` | `services/execution/` |
| `test_order_validator.py` | `services/execution/risk/` |
| `test_slippage.py` | `services/execution/simulation/` |
| `test_latency.py` | `services/execution/simulation/` |
| `test_execution_manager.py` | `services/execution/core/` |
| `test_audit.py` | `services/execution/` |
| `test_feature_engineering.py` | `services/signal/` |
| `test_sma_crossover.py` | `services/signal/strategies/` |
| `test_lightgbm_strategy.py` | `services/signal/strategies/` |
| `test_lstm_strategy.py` | `services/signal/strategies/` |
| `test_tft_strategy.py` | `services/signal/strategies/` |
| `test_lstm_model.py` | `services/signal/models/` |
| `test_tft_model.py` | `services/signal/models/` |
| `test_hybrid_model.py` | `services/signal/models/` |
| `test_xai_engine.py` | `services/signal/` |
| `test_synthetic_provider.py` | `services/gateway/providers/` |

CI runs `pytest tests/unit/ -v --tb=short` on every push/PR. Coverage reports
are produced by `pytest-cov` and uploaded as build artifacts.

---

## Historical Gap Analysis (pre-test baseline)

The sections below describe the state *before* unit tests were added. They are
kept as a record of what was prioritised and why.

### Original Coverage Estimate

| Area | Test files (original) | Estimated coverage |
|---|---|---|
| `services/risk/` | 0 | ~0% |
| `services/execution/` | 0 | ~0% |
| `services/signal/` | 0 | ~0% |
| `services/gateway/` | 0 | ~0% |
| `dashboard/` | 1 (utility only) | <5% |
| `tests/` (integration) | 1 (connectivity only) | N/A |

### Priority Rationale

Tests were prioritised in this order, driven by financial impact:

1. `test_risk_engine.py` — kill switch + position sizing (highest financial risk)
2. `test_portfolio.py` — average-price and cash accounting
3. `test_order_validator.py` — last gate before order submission
4. `test_slippage.py` — direction bug risk (BUY must pay more, SELL receives less)
5. `test_feature_engineering.py` — RSI bounds, ATR non-negativity, NaN handling
6. `test_sma_crossover.py` — warmup periods, crossover trigger logic
7. `test_execution_manager.py` — portfolio routing and orphan fills

### Original Infrastructure Gaps (now resolved)

| Gap | Resolution |
|---|---|
| No `pytest` in CI | `pytest` added to `ci.yml` |
| No `pyproject.toml` pytest config | `[tool.pytest.ini_options]` added |
| No `conftest.py` | `tests/unit/conftest.py` added with `sys.path` setup |
| No coverage reporting | `pytest-cov` added; XML report uploaded in CI |
