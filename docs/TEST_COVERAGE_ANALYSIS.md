# Test Coverage Analysis

## Executive Summary

The codebase currently has **near-zero test coverage** across all five microservices. Only 2 test files exist, covering trivial or infrastructure-only concerns. The risk engine, portfolio logic, and signal generation — the most financially consequential code — have no tests at all.

| Area | Test Files | Coverage Estimate |
|------|-----------|-------------------|
| `services/risk/` | 0 | ~0% |
| `services/execution/` | 0 | ~0% |
| `services/signal/` | 0 | ~0% |
| `services/gateway/` | 0 | ~0% |
| `dashboard/` | 1 (utility only) | <5% |
| `tests/` (integration) | 1 (connectivity only) | N/A |

---

## Existing Tests

### 1. `dashboard/lib/utils.test.ts` (Vitest)
Tests the `cn` Tailwind class-merge utility — 2 assertions covering basic merging and falsy filtering. This is not business logic; it wraps a third-party library (`tailwind-merge`).

### 2. `tests/integration_test.py`
Publishes one tick to a Redis channel, then waits 10 seconds to observe messages on `market_data`, `trade_signals`, `execution_requests`, and `execution_filled`. It only asserts Redis connectivity, not that the pipeline produces correct outputs. Single-tick injection will never trigger SMA crossover or LSTM signals due to their warmup requirements.

---

## Highest-Priority Gaps

### Priority 1 — `services/risk/risk_engine.py`

**Why critical:** This is the financial safety layer. Bugs here mean unchecked drawdowns, wrong position sizes, or ignored kill switches — all with direct monetary impact.

The `RiskEngine` class contains pure, deterministic logic with no external dependencies, making it ideal for unit testing.

**Untested behaviours:**

| Method | Scenarios missing tests |
|--------|------------------------|
| `check_kill_switch()` | Drawdown exactly at threshold, drawdown just below, consecutive losses exactly at limit, kill switch already active |
| `calculate_position_size()` | Kill switch active (must return 0), zero `risk_per_share` (stop == entry), normal sizing math, `current_equity = 0` |
| `validate_signal()` | Kill switch active, manual approval mode active, both inactive (happy path) |
| `record_prediction()` | Rolling window trim at `_window_size`, mixed correct/incorrect |
| `get_rolling_sharpe()` | Fewer than 5 data points (returns `None`), zero volatility (returns `None`), known return sequence producing a verifiable Sharpe |
| `get_rolling_accuracy()` | Fewer than 5 points, all correct, all wrong, mixed |
| `check_model_performance()` | Sharpe below threshold, accuracy below threshold, both below, already in manual mode (no double-trigger) |
| `reset_kill_switch()` | Starting equity is re-anchored, consecutive losses zeroed |

**Example test to write:**
```python
def test_kill_switch_activates_on_drawdown():
    engine = RiskEngine({"MAX_DAILY_LOSS_PCT": 0.03})
    engine.update_account_state(equity=100_000, daily_pnl=-3_000)
    assert engine.check_kill_switch() is True
    assert engine.is_kill_switch_active is True

def test_position_size_returns_zero_when_kill_switch_active():
    engine = RiskEngine({})
    engine.is_kill_switch_active = True
    assert engine.calculate_position_size(100.0, 95.0) == 0
```

---

### Priority 2 — `services/execution/core/portfolio.py`

**Why critical:** `VirtualPortfolio.update_from_fill` manages cash and average-price calculations. An averaging bug silently corrupts all P&L reporting.

**Untested behaviours:**

| Method | Scenarios missing tests |
|--------|------------------------|
| `update_from_fill()` | Buy creates new position; second buy updates average price correctly; sell reduces position; sell to exactly zero removes position from dict; sell when no position exists |
| `can_afford()` | Sufficient cash (true), insufficient cash (false), zero-cost sell (always true) |
| `get_market_value()` | With positions and known prices; fallback to `avg_price` when price missing |
| `calculate_total_equity()` | Accounts for cash + market value sum |
| `total_equity` property | Returns only `cash` (current placeholder — this is a known bug worth a test to document the limitation) |

**Example test to write:**
```python
def test_average_price_updated_correctly_on_second_buy():
    vp = VirtualPortfolio("test", starting_cash=100_000)
    vp.update_from_fill({"symbol": "AAPL", "qty": 10, "price": 100.0, "side": "buy", "timestamp": "..."})
    vp.update_from_fill({"symbol": "AAPL", "qty": 10, "price": 120.0, "side": "buy", "timestamp": "..."})
    assert vp.positions["AAPL"]["avg_price"] == 110.0
    assert vp.positions["AAPL"]["qty"] == 20
```

---

### Priority 3 — `services/execution/risk/validator.py`

**Why critical:** `OrderValidator.validate` is the last gate before a trade is sent. An incorrect rejection or acceptance directly causes missed or bad trades.

**Untested behaviours:**

| Scenario | Expected result |
|----------|----------------|
| `qty <= 0` | Rejected |
| `signal_price <= 0` | Rejected |
| BUY with insufficient cash | Rejected |
| BUY where `estimated_cost > MAX_ORDER_VALUE` ($50k) | Rejected |
| BUY where post-trade position value > `MAX_POS_SIZE` ($25k) | Rejected |
| SELL with no cash check | Accepted (sell is always cash-positive) |
| Valid BUY within all limits | Accepted |
| Existing position partially filled, new trade pushes over limit | Rejected |

---

### Priority 4 — `services/signal/feature_engineering.py`

**Why critical:** `FeatureEngineer.calculate_features` produces the feature matrix fed directly into the ML models. Silently wrong features produce silently wrong signals.

**Untested behaviours:**

- Empty DataFrame returns immediately without error
- All five required columns must be present for numeric coercion to succeed
- RSI values are bounded in [0, 100]
- ATR values are non-negative
- Bollinger upper band ≥ middle band ≥ lower band
- `dropna` removes rows with insufficient lookback (verify row count reduction is expected)
- Non-numeric strings in `close` column raise or are coerced gracefully

---

### Priority 5 — `services/signal/strategies/sma_crossover.py`

**Why important:** Strategy logic must produce signals at the right crossover point and suppress duplicate signals.

**Untested behaviours:**

| Scenario | Expected signal |
|----------|----------------|
| Fewer than `slow_period` ticks | `None` |
| Fast SMA crosses above slow SMA while not already LONG | `BUY` |
| Already LONG, fast still above slow | `None` (no duplicate) |
| Fast SMA crosses below slow SMA while LONG | `SELL` |
| Price of 0 or negative | `None` |

The async `on_tick` interface can be tested with `asyncio.run()` or `pytest-asyncio`.

---

### Priority 6 — `services/execution/simulation/slippage.py`

**Why important:** Slippage direction is inverted for BUY vs. SELL. A sign error here corrupts all simulated P&L.

**Untested behaviours:**

- BUY always returns a price **greater than** `decision_price`
- SELL always returns a price **less than** `decision_price`
- `decision_price <= 0` is returned unchanged
- Larger `qty` produces larger impact (statistical tendency, test with seeded RNG)
- `base_bps=0` still may have noise but no base component

---

### Priority 7 — `services/execution/core/manager.py`

**Untested behaviours:**

- Creating the same portfolio twice returns the existing one
- `register_order` + `on_execution_fill` routes fill to the correct portfolio
- Fill with unknown `order_id` but matching `model_id` uses fallback routing
- Fill with no matching portfolio logs an orphan warning

---

## Infrastructure Gaps

### No CI test execution for Python

The `.github/workflows/ci.yml` runs `flake8` but does **not** run `pytest`. All Python unit tests would be invisible to CI until this is added:

```yaml
- name: Run unit tests
  run: |
    pip install pytest pytest-asyncio pandas numpy ta
    pytest tests/unit/ -v
```

### No `pytest` configuration

There is no `pytest.ini`, `pyproject.toml` `[tool.pytest.ini_options]`, or `conftest.py`. Adding a minimal `pyproject.toml` would allow consistent test discovery and settings (e.g. asyncio mode for strategy tests).

### No coverage reporting

No coverage tool (`coverage.py`, `pytest-cov`) is configured. Adding `pytest --cov=services` would immediately surface which lines are hit.

---

## Recommended Implementation Order

1. **`tests/unit/test_risk_engine.py`** — Pure Python, no deps, highest financial impact. Can be written and run immediately.
2. **`tests/unit/test_portfolio.py`** — Pure Python, no deps, catches averaging and position-management bugs.
3. **`tests/unit/test_order_validator.py`** — Pure Python, depends only on `VirtualPortfolio`.
4. **`tests/unit/test_slippage.py`** — Pure Python, test with `random.seed()` for determinism.
5. **`tests/unit/test_feature_engineering.py`** — Requires `pandas` + `ta`. Use small synthetic DataFrames.
6. **`tests/unit/test_sma_crossover.py`** — Requires `pytest-asyncio`.
7. **Expand `tests/integration_test.py`** — Inject enough ticks to trigger SMA warmup; assert `trade_signals` channel receives a message.
8. **Add dashboard component tests** — `@testing-library/react` for `SignalFeed`, `TradeLog`, `MetricsGrid` render/data-binding.

---

## Quick Wins

The following can be added in a single session with no new dependencies:

- `test_risk_engine.py`: ~15 test cases, pure Python
- `test_portfolio.py`: ~10 test cases, pure Python
- `test_slippage.py`: ~5 test cases, pure Python with `random.seed()`

These three files alone would provide meaningful coverage of the most risk-sensitive code paths and could be run in CI immediately.
