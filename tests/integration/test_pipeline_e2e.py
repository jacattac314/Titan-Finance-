"""
tests/integration/test_pipeline_e2e.py
=======================================
End-to-end integration tests for the Signal → Risk → Execution → Feedback loop.

Tests exercise real module instances (no mocking) and verify:

  1. Risk validates trade_signals and produces execution_requests.
  2. execution_requests payloads from Risk are consumable by Execution's fill
     logic (payload compatibility — the bridge we wired in execution/main.py).
  3. Execution fills correctly update Virtual Portfolio state.
  4. execution_filled events fed back to Risk correctly update rolling metrics
     (Sharpe, accuracy, consecutive-loss counter, kill switch).
  5. Kill switch halts the pipeline end-to-end after sufficient losses.
  6. Multi-model portfolios are fully isolated from one another.

No Redis, no Alpaca API, no Docker — all logic runs in-process.
"""

import uuid
import datetime
import pytest

from risk_engine import RiskEngine
from core.manager import PortfolioManager
from risk.validator import OrderValidator
from simulation.slippage import SlippageModel
from simulation.latency import LatencySimulator


# ---------------------------------------------------------------------------
# Constants — chosen so Risk-sized orders stay within OrderValidator limits:
#   MAX_ORDER_VALUE = $50,000
#   MAX_POS_SIZE    = $25,000
#
# Using RISK_PER_TRADE_PCT=0.001 (0.1%):
#   risk_amount = $100 on a $100k account
#   With price=$150, stop=$147 → risk_per_share=$3 → units=33, cost=$4,950  ✓
# ---------------------------------------------------------------------------

_PRICE = 150.0
_STOP = 147.0   # 2% below price, matches risk/main.py's BUY stop formula
_EQUITY = 100_000.0
_RISK_PCT = 0.001   # 0.1% per trade — keeps order value well under validator limits


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def make_risk_engine(**overrides) -> RiskEngine:
    cfg = {
        "MAX_DAILY_LOSS_PCT": 0.03,
        "RISK_PER_TRADE_PCT": _RISK_PCT,
        "MAX_CONSECUTIVE_LOSSES": 5,
        "ROLLBACK_MIN_SHARPE": 0.50,
        "ROLLBACK_MIN_ACCURACY": 0.50,
    }
    cfg.update(overrides)
    return RiskEngine(cfg)


def make_trade_signal(**overrides) -> dict:
    """Realistic trade_signals payload (as published by services/signal)."""
    sig = {
        "model_id": "test_model",
        "symbol": "AAPL",
        "signal": "BUY",
        "confidence": 0.82,
        "price": _PRICE,
        "explanation": [{"feature": "rsi", "value": 0.6}],
        "timestamp": "2026-02-25T00:00:00Z",
    }
    sig.update(overrides)
    return sig


def risk_process_signal(engine: RiskEngine, signal: dict) -> dict | None:
    """
    Replicate risk/main.py's per-message logic:
      validate → kill-switch check → position size → build execution_payload.

    Returns the execution_requests payload or None if the signal is blocked.
    """
    if not engine.validate_signal(signal):
        return None

    if engine.check_kill_switch():
        return None

    price = float(signal.get("price", 0) or 0)
    if price <= 0:
        return None

    stop_loss = price * (0.98 if signal.get("signal") == "BUY" else 1.02)
    units = engine.calculate_position_size(price, stop_loss)
    if units <= 0:
        return None

    return {
        "model_id": signal.get("model_id", "unknown"),
        "symbol": signal["symbol"],
        "qty": units,
        "side": "buy" if signal.get("signal") == "BUY" else "sell",
        "type": "market",
        "confidence": signal.get("confidence", 0.0),
        "explanation": signal.get("explanation", []),
        "timestamp": signal.get("timestamp"),
    }


async def execution_fill(
    execution_req: dict,
    current_price: float,
    manager: PortfolioManager,
) -> dict | None:
    """
    Replicate execution/main.py's simulate_fill using the underlying modules
    directly (no module-level singleton imports needed in tests).

    Uses zero-latency simulator so tests run instantly.
    """
    validator = OrderValidator()
    slippage_model = SlippageModel()
    latency_sim = LatencySimulator(min_ms=0, max_ms=0)

    model_id = execution_req.get("model_id", "default_model")
    side = (execution_req.get("side") or execution_req.get("signal") or "").upper()
    symbol = execution_req.get("symbol")
    decision_price = float(execution_req.get("price") or current_price or 0.0)

    if decision_price <= 0:
        return None

    portfolio = manager.get_portfolio(model_id) or manager.create_portfolio(model_id)

    risk_qty = execution_req.get("qty")
    qty = 0
    if side == "BUY":
        if portfolio.cash < 10.0:
            return None
        qty = int(risk_qty) if risk_qty else int(min(portfolio.cash, 10_000.0) / decision_price)
    elif side == "SELL":
        pos = portfolio.positions.get(symbol)
        if not pos or pos["qty"] <= 0:
            return None
        qty = int(risk_qty) if risk_qty else pos["qty"]

    if qty <= 0:
        return None

    if not validator.validate(portfolio, symbol, decision_price, qty, side):
        return None

    await latency_sim.delay()
    executed_price = slippage_model.calculate_price(decision_price, side, qty)

    return {
        "id": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "model_id": model_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": executed_price,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "FILLED",
        "mode": "paper",
        "slippage": round(executed_price - decision_price, 4),
        "explanation": execution_req.get("explanation", []),
    }


# ---------------------------------------------------------------------------
# 1. Signal → Risk: validate and size
# ---------------------------------------------------------------------------

class TestSignalToRiskPayload:
    """Risk validates trade_signals and produces well-formed execution_requests."""

    def test_valid_buy_signal_forwarded(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        payload = risk_process_signal(engine, make_trade_signal())

        assert payload is not None
        assert payload["symbol"] == "AAPL"
        assert payload["side"] == "buy"
        assert payload["qty"] > 0

    def test_valid_sell_signal_forwarded(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        payload = risk_process_signal(engine, make_trade_signal(signal="SELL"))

        assert payload is not None
        assert payload["side"] == "sell"

    def test_execution_payload_contains_required_keys(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        payload = risk_process_signal(engine, make_trade_signal())

        required = {"model_id", "symbol", "qty", "side", "type", "confidence"}
        assert required <= set(payload.keys()), (
            f"execution_requests payload missing keys: {required - set(payload.keys())}"
        )

    def test_position_sizing_scales_with_equity(self):
        """Higher account equity → larger position size."""
        small = make_risk_engine(RISK_PER_TRADE_PCT=_RISK_PCT)
        small.update_account_state(equity=10_000, daily_pnl=0)
        large = make_risk_engine(RISK_PER_TRADE_PCT=_RISK_PCT)
        large.update_account_state(equity=100_000, daily_pnl=0)

        sig = make_trade_signal()
        assert risk_process_signal(large, sig)["qty"] > risk_process_signal(small, sig)["qty"]

    def test_kill_switch_blocks_forwarding(self):
        engine = make_risk_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=96_000, daily_pnl=-4_000)  # 4% > 3% limit
        assert risk_process_signal(engine, make_trade_signal()) is None

    def test_manual_approval_mode_blocks_forwarding(self):
        engine = make_risk_engine()
        engine.is_manual_approval_mode = True
        assert risk_process_signal(engine, make_trade_signal()) is None

    def test_missing_price_blocks_forwarding(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        assert risk_process_signal(engine, make_trade_signal(price=0)) is None


# ---------------------------------------------------------------------------
# 2. Risk → Execution: payload compatibility
# ---------------------------------------------------------------------------

class TestRiskToExecutionPayloadCompatibility:
    """execution_requests payload produced by Risk is consumable by Execution."""

    async def test_execution_request_produces_fill(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        exec_req = risk_process_signal(engine, make_trade_signal(price=_PRICE))

        assert exec_req is not None, "pre-condition: Risk should approve signal"

        manager = PortfolioManager()
        fill = await execution_fill(exec_req, current_price=_PRICE, manager=manager)

        assert fill is not None, "Execution must produce a fill from a valid execution_request"
        assert fill["symbol"] == "AAPL"
        assert fill["side"] == "BUY"
        assert fill["qty"] == exec_req["qty"], (
            "Execution should honour Risk's pre-calculated qty"
        )
        assert fill["status"] == "FILLED"
        assert fill["mode"] == "paper"

    async def test_fill_price_within_1pct_of_signal_price(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        exec_req = risk_process_signal(engine, make_trade_signal(price=_PRICE))

        manager = PortfolioManager()
        fill = await execution_fill(exec_req, current_price=_PRICE, manager=manager)

        assert fill is not None
        pct_diff = abs(fill["price"] - _PRICE) / _PRICE
        assert pct_diff < 0.01, f"Slippage {pct_diff:.2%} exceeds 1% — SlippageModel may be miscalibrated"

    async def test_buy_slippage_increases_price(self):
        """BUY orders must execute at ≥ decision price (adverse slippage)."""
        exec_req = {
            "model_id": "m1", "symbol": "AAPL", "qty": 10,
            "side": "buy", "type": "market", "confidence": 0.8,
        }
        manager = PortfolioManager()
        fill = await execution_fill(exec_req, current_price=100.0, manager=manager)

        assert fill is not None
        assert fill["price"] >= 100.0, "BUY fill price must be ≥ decision price"

    async def test_payload_without_qty_falls_back_to_internal_sizing(self):
        """Execution handles payloads with no qty field (legacy / direct injection)."""
        req = {
            "model_id": "legacy", "symbol": "TSLA",
            "side": "buy", "type": "market", "confidence": 0.7,
        }
        manager = PortfolioManager()
        fill = await execution_fill(req, current_price=100.0, manager=manager)

        assert fill is not None
        assert fill["qty"] > 0


# ---------------------------------------------------------------------------
# 3. Execution → Portfolio: state updates
# ---------------------------------------------------------------------------

class TestPortfolioStateAfterFill:
    """VirtualPortfolio is updated correctly after execution fills."""

    async def test_buy_reduces_cash_and_opens_position(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        exec_req = risk_process_signal(engine, make_trade_signal(price=_PRICE))

        manager = PortfolioManager()
        portfolio = manager.create_portfolio(exec_req["model_id"], starting_cash=_EQUITY)
        starting_cash = portfolio.cash

        fill = await execution_fill(exec_req, current_price=_PRICE, manager=manager)
        assert fill is not None
        manager.on_execution_fill(fill)

        assert portfolio.cash < starting_cash, "Cash must decrease after BUY"
        assert "AAPL" in portfolio.positions
        assert portfolio.positions["AAPL"]["qty"] > 0

    async def test_round_trip_buy_sell_closes_position(self):
        manager = PortfolioManager()
        model_id = "round_trip_model"
        manager.create_portfolio(model_id, starting_cash=_EQUITY)

        buy = {
            "id": str(uuid.uuid4()), "order_id": str(uuid.uuid4()),
            "model_id": model_id, "symbol": "MSFT",
            "side": "BUY", "qty": 10, "price": 400.0,
            "status": "FILLED", "mode": "paper", "slippage": 0.0, "explanation": [],
        }
        manager.on_execution_fill(buy)
        assert "MSFT" in manager.get_portfolio(model_id).positions

        sell = {**buy, "id": str(uuid.uuid4()), "order_id": str(uuid.uuid4()), "side": "SELL"}
        manager.on_execution_fill(sell)
        assert "MSFT" not in manager.get_portfolio(model_id).positions

    def test_profitable_round_trip_increases_equity(self):
        manager = PortfolioManager()
        model_id = "equity_test"
        manager.create_portfolio(model_id, starting_cash=100_000.0)

        buy = {
            "id": "f1", "order_id": "o1",
            "model_id": model_id, "symbol": "NVDA",
            "side": "BUY", "qty": 100, "price": 500.0,
            "status": "FILLED", "mode": "paper", "slippage": 0.0, "explanation": [],
        }
        sell = {**buy, "id": "f2", "order_id": "o2", "side": "SELL", "price": 550.0}

        manager.on_execution_fill(buy)
        manager.on_execution_fill(sell)

        portfolio = manager.get_portfolio(model_id)
        expected_cash = 100_000.0 + (100 * 50.0)   # 100 shares × $50 gain
        assert abs(portfolio.cash - expected_cash) < 0.01

    def test_multi_model_portfolios_are_isolated(self):
        manager = PortfolioManager()
        manager.create_portfolio("model_a", starting_cash=100_000.0)
        manager.create_portfolio("model_b", starting_cash=100_000.0)

        fill_a = {
            "id": "f1", "order_id": "o1",
            "model_id": "model_a", "symbol": "AAPL",
            "side": "BUY", "qty": 100, "price": 150.0,
            "status": "FILLED", "mode": "paper", "slippage": 0.0, "explanation": [],
        }
        manager.on_execution_fill(fill_a)

        assert manager.get_portfolio("model_a").cash < 100_000.0, "model_a cash should decrease"
        assert manager.get_portfolio("model_b").cash == 100_000.0, "model_b must be unaffected"
        assert "AAPL" in manager.get_portfolio("model_a").positions
        assert "AAPL" not in manager.get_portfolio("model_b").positions


# ---------------------------------------------------------------------------
# 4. Execution → Risk feedback: rolling metrics updated
# ---------------------------------------------------------------------------

class TestRiskFeedbackLoop:
    """execution_filled events fed back to Risk correctly update rolling metrics."""

    def _risk_feedback_from_fill(self, engine: RiskEngine, fill: dict):
        """
        Replicate risk/main.py's execution_filled handler:
        extract a simple return from slippage and feed it to the engine.
        """
        price = float(fill.get("price", 0) or 0)
        slippage = float(fill.get("slippage", 0) or 0)
        side = fill.get("side", "BUY").upper()

        if price > 0:
            raw_return = -slippage / price
            correct_direction = raw_return >= 0 if side == "BUY" else raw_return <= 0
            engine.record_trade_result(raw_return)
            engine.record_prediction(correct_direction, raw_return)

    def test_fill_with_positive_slippage_increments_loss_counter(self):
        """Slippage is a cost → negative return → consecutive loss +1."""
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)

        fill = {"price": 150.0, "slippage": 1.50, "side": "BUY"}
        self._risk_feedback_from_fill(engine, fill)

        assert engine.consecutive_losses == 1

    def test_five_bad_fills_trigger_kill_switch(self):
        engine = make_risk_engine(MAX_CONSECUTIVE_LOSSES=5)
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)

        for _ in range(5):
            engine.record_trade_result(-100.0)

        assert engine.check_kill_switch() is True

    def test_ten_wrong_predictions_trigger_model_rollback(self):
        engine = make_risk_engine(ROLLBACK_MIN_ACCURACY=0.50)

        for i in range(10):
            is_correct = i < 2            # 2 correct, 8 wrong → accuracy 0.20 < threshold
            engine.record_prediction(is_correct, 0.01 if is_correct else -0.01)

        assert engine.check_model_performance() is True
        assert engine.is_manual_approval_mode is True

    def test_fill_feedback_accumulates_across_multiple_trades(self):
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)

        fills = [
            {"price": 150.0, "slippage": 0.75, "side": "BUY"},   # small cost
            {"price": 160.0, "slippage": 0.80, "side": "BUY"},
            {"price": 155.0, "slippage": 0.78, "side": "BUY"},
        ]
        for fill in fills:
            self._risk_feedback_from_fill(engine, fill)

        # 3 fills fed back — consecutive_losses should be 3 (all slippage = cost)
        assert engine.consecutive_losses == 3


# ---------------------------------------------------------------------------
# 5. Full pipeline: end-to-end scenarios
# ---------------------------------------------------------------------------

class TestFullPipelineScenarios:
    """Complete Signal → Risk → Execution → Feedback scenarios."""

    async def test_happy_path_buy_signal_end_to_end(self):
        """
        A single BUY signal flows through all three hops and leaves
        consistent state in Risk engine and Virtual Portfolio.
        """
        # ── 1. Risk validates and sizes the signal ───────────────────────
        engine = make_risk_engine()
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)
        signal = make_trade_signal(symbol="GOOG", price=_PRICE, confidence=0.91)

        exec_req = risk_process_signal(engine, signal)
        assert exec_req is not None
        assert exec_req["side"] == "buy"
        assert exec_req["qty"] > 0

        # ── 2. Execution fills the order ─────────────────────────────────
        manager = PortfolioManager()
        manager.create_portfolio(exec_req["model_id"], starting_cash=_EQUITY)

        fill = await execution_fill(exec_req, current_price=_PRICE, manager=manager)
        assert fill is not None
        assert fill["status"] == "FILLED"

        # ── 3. Portfolio reflects the fill ───────────────────────────────
        manager.on_execution_fill(fill)
        portfolio = manager.get_portfolio(exec_req["model_id"])
        assert "GOOG" in portfolio.positions

        # ── 4. Risk records feedback from execution_filled ───────────────
        price = fill["price"]
        slippage = fill["slippage"]
        raw_return = -abs(slippage) / price
        engine.record_trade_result(raw_return)
        engine.record_prediction(raw_return >= 0, raw_return)

        # One small-cost trade should not trigger the kill switch
        assert engine.is_kill_switch_active is False

    async def test_kill_switch_halts_pipeline_after_losses(self):
        """
        After MAX_CONSECUTIVE_LOSSES losing fills, the kill switch fires
        and all subsequent signals are blocked.
        """
        engine = make_risk_engine(MAX_CONSECUTIVE_LOSSES=3)
        engine.update_account_state(equity=_EQUITY, daily_pnl=0)

        signal = make_trade_signal()

        # First signal passes through Risk
        payload_1 = risk_process_signal(engine, signal)
        assert payload_1 is not None

        # Three consecutive losing fills fed back to Risk
        for _ in range(3):
            engine.record_trade_result(-500.0)

        engine.check_kill_switch()   # evaluate after each batch in real service

        # Subsequent signal is now blocked
        payload_2 = risk_process_signal(engine, signal)
        assert payload_2 is None, "Kill switch must block all signals after threshold"

    async def test_multi_model_arena_isolates_each_contender(self):
        """
        Fills for model_a must not bleed into model_b's portfolio.
        Each contender has its own independent ledger.
        """
        engine_a = make_risk_engine()
        engine_b = make_risk_engine()
        engine_a.update_account_state(equity=_EQUITY, daily_pnl=0)
        engine_b.update_account_state(equity=_EQUITY, daily_pnl=0)

        sig_a = make_trade_signal(model_id="model_a", symbol="AAPL")
        sig_b = make_trade_signal(model_id="model_b", symbol="TSLA", price=_PRICE)

        req_a = risk_process_signal(engine_a, sig_a)
        req_b = risk_process_signal(engine_b, sig_b)
        assert req_a is not None
        assert req_b is not None

        manager = PortfolioManager()
        manager.create_portfolio("model_a", starting_cash=_EQUITY)
        manager.create_portfolio("model_b", starting_cash=_EQUITY)

        fill_a = await execution_fill(req_a, current_price=_PRICE, manager=manager)
        fill_b = await execution_fill(req_b, current_price=_PRICE, manager=manager)
        assert fill_a is not None
        assert fill_b is not None

        manager.on_execution_fill(fill_a)
        manager.on_execution_fill(fill_b)

        port_a = manager.get_portfolio("model_a")
        port_b = manager.get_portfolio("model_b")

        assert port_a.cash < _EQUITY, "model_a cash should have decreased"
        assert port_b.cash < _EQUITY, "model_b cash should have decreased"
        assert "AAPL" in port_a.positions and "TSLA" not in port_a.positions
        assert "TSLA" in port_b.positions and "AAPL" not in port_b.positions
