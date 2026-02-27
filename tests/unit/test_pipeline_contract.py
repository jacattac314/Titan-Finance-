"""
End-to-end pipeline contract test.

Validates that the payload schemas flowing between services are mutually
compatible at every hop — no running processes required.

Pipeline under test:

    market_data tick
        │
        ▼  [SMACrossover.on_tick]
    trade_signals payload            ← schema validated here
        │
        ▼  [RiskEngine.validate_signal + calculate_position_size]
    execution_requests payload       ← schema validated here
        │                              (built exactly as risk/main.py does)
        ▼  [simulate_fill]
    execution_filled payload         ← schema validated here

Additionally asserts the negative case: passing a raw trade_signals payload
directly to simulate_fill (bypassing risk) must return None — demonstrating
exactly the bypass that the P0 fix closed.
"""
import importlib.util
import math
import pathlib
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Bootstrap — mock external deps, ensure correct service paths
# ---------------------------------------------------------------------------

# Mock unavailable packages before any service import touches them.
for _mod in ("dotenv", "redis", "redis.asyncio", "alpaca_client", "audit"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["redis"].from_url = MagicMock(return_value=MagicMock())

_REPO = pathlib.Path(__file__).parent.parent.parent
_EXEC_DIR = _REPO / "services" / "execution"
_exec_dir_str = str(_EXEC_DIR)
if _exec_dir_str not in sys.path:
    sys.path.insert(0, _exec_dir_str)

# Load services/execution/main.py by explicit path to avoid sys.path ambiguity.
_spec = importlib.util.spec_from_file_location("exec_main_pipe", _EXEC_DIR / "main.py")
_exec_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_exec_main)
simulate_fill = _exec_main.simulate_fill

# Direct imports — conftest.py adds services/{risk,signal,execution} to sys.path.
from strategies.sma_crossover import SMACrossover  # services/signal
from risk_engine import RiskEngine                  # services/risk
from core.manager import PortfolioManager           # services/execution

# ---------------------------------------------------------------------------
# Expected schemas — the contracts between each pair of services
# ---------------------------------------------------------------------------

# Fields that risk/main.py reads from a trade_signals message
_TRADE_SIGNAL_REQUIRED = {"model_id", "symbol", "signal", "price", "confidence"}

# Fields that execution/main.py reads from an execution_requests message
_EXECUTION_REQUEST_REQUIRED = {
    "model_id", "symbol", "qty", "side", "type", "confidence", "timestamp",
}

# Fields that execution/main.py publishes in every execution_filled message
_EXECUTION_FILLED_REQUIRED = {
    "id", "order_id", "model_id", "symbol", "side", "qty",
    "price", "timestamp", "status", "mode", "slippage", "explanation",
}

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

_SMA_CONFIG = {
    "model_id": "sma_spy_pipeline_test",
    "symbol": "SPY",
    "fast_period": 5,
    "slow_period": 10,
}

_RISK_CONFIG = {
    "MAX_DAILY_LOSS_PCT": 0.03,
    "RISK_PER_TRADE_PCT": 0.01,
    "MAX_CONSECUTIVE_LOSSES": 5,
    "ROLLBACK_MIN_SHARPE": 0.5,
    "ROLLBACK_MIN_ACCURACY": 0.50,
}

# Price sequence chosen to produce a golden cross (BUY) on tick 10.
# Ticks 1-9 hold price=80 (flat), tick 10 jumps to 120.
#   fast_sma (last 5) = mean([80, 80, 80, 80, 120]) = 88
#   slow_sma (all 10) = mean([80]*9 + [120])         = 84
#   88 > 84  →  BUY, price=120
_TICKS = [{"symbol": "SPY", "price": 80.0, "timestamp": f"2024-01-01T09:3{i}:00Z"}
          for i in range(9)]
_TICKS.append({"symbol": "SPY", "price": 120.0, "timestamp": "2024-01-01T09:39:00Z"})


async def _drive_signal() -> dict:
    """Feed the price sequence into SMACrossover; return the BUY signal dict."""
    strategy = SMACrossover(_SMA_CONFIG)
    signal = None
    for tick in _TICKS:
        result = await strategy.on_tick(tick)
        if result is not None:
            signal = result
            break
    assert signal is not None, "SMACrossover did not produce a signal — check _TICKS"
    return signal


def _build_execution_request(signal: dict, engine: RiskEngine) -> dict:
    """
    Replicate exactly what risk/main.py does when it approves a signal:
    validate → position-size → build execution_requests payload.
    Returns None if the signal is blocked by risk.
    """
    if not engine.validate_signal(signal):
        return None

    price = float(signal["price"])
    stop_loss = price * (0.98 if signal["signal"] == "BUY" else 1.02)
    units = engine.calculate_position_size(price, stop_loss)

    if units <= 0:
        return None

    return {
        "model_id": signal.get("model_id", "unknown"),
        "symbol": signal["symbol"],
        "qty": units,
        "side": "buy" if signal["signal"] == "BUY" else "sell",
        "type": "market",
        "confidence": signal.get("confidence", 0.0),
        "explanation": signal.get("explanation", []),
        "timestamp": signal.get("timestamp"),
    }


def _make_engine(equity: float = 50_000.0) -> RiskEngine:
    engine = RiskEngine(_RISK_CONFIG)
    engine.update_account_state(equity=equity, daily_pnl=0.0)
    return engine


# ---------------------------------------------------------------------------
# Hop 1: Signal service → trade_signals schema contract
# ---------------------------------------------------------------------------

class TestTradeSignalSchema:
    """SMACrossover must emit all fields that RiskGuardian reads."""

    async def test_signal_carries_required_fields(self):
        signal = await _drive_signal()
        missing = _TRADE_SIGNAL_REQUIRED - signal.keys()
        assert not missing, (
            f"trade_signals payload missing fields expected by RiskGuardian: {missing}"
        )

    async def test_signal_value_is_buy_or_sell(self):
        signal = await _drive_signal()
        assert signal["signal"] in ("BUY", "SELL", "HOLD"), (
            f"signal must be BUY/SELL/HOLD, got: {signal['signal']}"
        )

    async def test_price_is_positive(self):
        signal = await _drive_signal()
        assert float(signal["price"]) > 0

    async def test_confidence_is_in_unit_range(self):
        signal = await _drive_signal()
        assert 0.0 <= float(signal["confidence"]) <= 1.0

    async def test_symbol_matches_strategy_config(self):
        signal = await _drive_signal()
        assert signal["symbol"] == _SMA_CONFIG["symbol"]

    async def test_model_id_matches_strategy_config(self):
        signal = await _drive_signal()
        assert signal["model_id"] == _SMA_CONFIG["model_id"]


# ---------------------------------------------------------------------------
# Hop 2: RiskGuardian → execution_requests schema contract
# ---------------------------------------------------------------------------

class TestExecutionRequestSchema:
    """RiskGuardian must emit all fields that ExecutionService reads."""

    async def test_execution_request_carries_required_fields(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None, "RiskEngine blocked a valid signal unexpectedly"
        missing = _EXECUTION_REQUEST_REQUIRED - req.keys()
        assert not missing, (
            f"execution_requests payload missing fields expected by ExecutionService: {missing}"
        )

    async def test_side_is_lowercase(self):
        """RiskGuardian publishes lowercase 'buy'/'sell'; ExecutionService normalises."""
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        assert req["side"] in ("buy", "sell"), (
            f"execution_requests side must be lowercase 'buy' or 'sell', got: {req['side']}"
        )

    async def test_qty_is_positive_integer(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        assert isinstance(req["qty"], int) and req["qty"] > 0, (
            f"execution_requests qty must be a positive int, got: {req['qty']}"
        )

    async def test_qty_matches_fixed_fractional_formula(self):
        """Verify the position size is calculated with the Fixed Fractional formula."""
        signal = await _drive_signal()
        engine = _make_engine(equity=50_000.0)
        req = _build_execution_request(signal, engine)
        assert req is not None

        price = float(signal["price"])
        stop_loss = price * 0.98
        expected_units = math.floor(
            (50_000.0 * _RISK_CONFIG["RISK_PER_TRADE_PCT"]) / abs(price - stop_loss)
        )
        assert req["qty"] == expected_units, (
            f"Expected qty={expected_units} from Fixed Fractional formula, got {req['qty']}"
        )

    async def test_buy_signal_maps_to_lowercase_buy_side(self):
        signal = await _drive_signal()
        assert signal["signal"] == "BUY"
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        assert req["side"] == "buy"

    async def test_type_is_market(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        assert req["type"] == "market"

    async def test_confidence_preserved_from_signal(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        assert req["confidence"] == signal["confidence"]

    async def test_kill_switch_blocks_execution_request(self):
        """When kill switch is active, no execution_request must be built."""
        signal = await _drive_signal()
        engine = _make_engine()
        engine.is_kill_switch_active = True
        req = _build_execution_request(signal, engine)
        assert req is None, "Kill switch must prevent execution_request from being built"


# ---------------------------------------------------------------------------
# Hop 3: ExecutionService → execution_filled schema contract
# ---------------------------------------------------------------------------

class TestExecutionFillSchema:
    """simulate_fill must emit all fields consumed by dashboard and RiskGuardian."""

    async def test_fill_carries_required_fields(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None

        manager = PortfolioManager()
        fill = await simulate_fill(req, current_price=float(signal["price"]), manager=manager)
        assert fill is not None, "simulate_fill returned None for a valid execution_request"

        missing = _EXECUTION_FILLED_REQUIRED - fill.keys()
        assert not missing, (
            f"execution_filled payload missing fields: {missing}"
        )

    async def test_fill_side_is_uppercase(self):
        """ExecutionService normalises the lowercase side from risk to uppercase."""
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        manager = PortfolioManager()
        fill = await simulate_fill(req, current_price=float(signal["price"]), manager=manager)
        assert fill is not None
        assert fill["side"] in ("BUY", "SELL"), (
            f"execution_filled side must be uppercase BUY/SELL, got: {fill['side']}"
        )

    async def test_fill_qty_matches_request(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        manager = PortfolioManager()
        fill = await simulate_fill(req, current_price=float(signal["price"]), manager=manager)
        assert fill is not None
        assert fill["qty"] == req["qty"]

    async def test_fill_status_is_filled(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        manager = PortfolioManager()
        fill = await simulate_fill(req, current_price=float(signal["price"]), manager=manager)
        assert fill is not None
        assert fill["status"] == "FILLED"

    async def test_fill_mode_is_paper(self):
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        manager = PortfolioManager()
        fill = await simulate_fill(req, current_price=float(signal["price"]), manager=manager)
        assert fill is not None
        assert fill["mode"] == "paper"

    async def test_slippage_is_buy_adverse(self):
        """For a BUY, slippage must be positive (execution price > decision price)."""
        signal = await _drive_signal()
        req = _build_execution_request(signal, _make_engine())
        assert req is not None
        manager = PortfolioManager()
        fill = await simulate_fill(req, current_price=float(signal["price"]), manager=manager)
        assert fill is not None
        assert fill["slippage"] >= 0, (
            f"BUY fill slippage must be non-negative (adverse), got: {fill['slippage']}"
        )


# ---------------------------------------------------------------------------
# Negative: bypass detection
# ---------------------------------------------------------------------------

class TestRiskBypassIsBlocked:
    """
    Demonstrate the exact bypass that the P0 fix closed:
    a raw trade_signals payload passed directly to simulate_fill
    must NEVER produce a fill.
    """

    async def test_raw_signal_bypassing_risk_produces_no_fill(self):
        """
        trade_signals format has 'signal' (not 'side') and no 'qty'.
        Passing it directly to simulate_fill must return None.
        """
        signal = await _drive_signal()
        # signal dict is the raw trade_signals payload — do NOT transform via risk
        manager = PortfolioManager()
        fill = await simulate_fill(signal, current_price=float(signal["price"]), manager=manager)
        assert fill is None, (
            "Passing a raw trade_signals payload directly to simulate_fill "
            "must return None. Risk gating was bypassed — this is the P0 bug."
        )

    async def test_signal_with_signal_key_and_no_qty_is_rejected(self):
        """Both the missing 'side' and missing 'qty' individually cause rejection."""
        signal = await _drive_signal()

        # Test: missing qty (trade_signals format)
        partial = {k: v for k, v in signal.items() if k != "signal"}
        partial["side"] = "BUY"   # uppercase — wrong format from risk
        partial.pop("qty", None)  # no qty
        manager = PortfolioManager()
        fill = await simulate_fill(partial, current_price=float(signal["price"]), manager=manager)
        assert fill is None, "Missing qty must be rejected"

    async def test_signal_with_qty_but_wrong_side_key_is_rejected(self):
        """Having qty but using 'signal' (not 'side') as the direction key → rejected."""
        signal = await _drive_signal()
        bad_req = {
            "model_id": signal["model_id"],
            "symbol": signal["symbol"],
            "qty": 10,
            "signal": "BUY",  # wrong key — simulate_fill reads 'side', not 'signal'
            "confidence": signal["confidence"],
            "timestamp": signal["timestamp"],
        }
        manager = PortfolioManager()
        fill = await simulate_fill(bad_req, current_price=float(signal["price"]), manager=manager)
        assert fill is None, (
            "A payload with 'signal' instead of 'side' must be rejected — "
            "simulate_fill must only read the 'side' key (risk-approved format)"
        )


# ---------------------------------------------------------------------------
# Full pipeline: single end-to-end traversal
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """
    Single test that walks all three hops and asserts the pipeline is intact.
    This is the regression guard — if any schema contract breaks between services,
    this test catches it.
    """

    async def test_market_tick_produces_valid_fill_via_risk(self):
        # Hop 1: Signal service
        signal = await _drive_signal()
        assert signal["signal"] == "BUY"
        assert _TRADE_SIGNAL_REQUIRED.issubset(signal.keys()), (
            f"trade_signals schema broken: {_TRADE_SIGNAL_REQUIRED - signal.keys()}"
        )

        # Hop 2: RiskGuardian
        engine = _make_engine(equity=50_000.0)
        req = _build_execution_request(signal, engine)
        assert req is not None, "RiskGuardian blocked a valid signal"
        assert _EXECUTION_REQUEST_REQUIRED.issubset(req.keys()), (
            f"execution_requests schema broken: {_EXECUTION_REQUEST_REQUIRED - req.keys()}"
        )
        assert req["side"] == "buy"       # risk publishes lowercase
        assert req["qty"] > 0

        # Hop 3: ExecutionService
        manager = PortfolioManager()
        fill = await simulate_fill(req, current_price=float(signal["price"]), manager=manager)
        assert fill is not None, "simulate_fill returned None for a risk-approved request"
        assert _EXECUTION_FILLED_REQUIRED.issubset(fill.keys()), (
            f"execution_filled schema broken: {_EXECUTION_FILLED_REQUIRED - fill.keys()}"
        )
        assert fill["side"] == "BUY"      # execution normalises to uppercase
        assert fill["qty"] == req["qty"]
        assert fill["status"] == "FILLED"
        assert fill["mode"] == "paper"
        assert fill["slippage"] >= 0      # adverse for BUY
