"""
End-to-end pipeline tests for TitanFlow.

These tests exercise the complete trading pipeline—from raw market data ticks
all the way through to execution fills—without requiring any external services
(Redis, PostgreSQL, Alpaca).  External I/O is replaced by direct function calls
and lightweight mocking so the full business logic can be validated in CI.

Pipeline under test:
    market_data tick
        → SMACrossover.on_tick()         [signal service]
        → RiskEngine.validate_signal()   [risk service]
        → RiskEngine.calculate_position_size()
        → simulate_fill()                [execution service]
        → VirtualPortfolio.update_from_fill()

Additional scenarios:
    • Kill-switch activation blocks all downstream signals.
    • Manual-approval mode suspends auto-execution.
    • Malformed events are rejected at every schema boundary.
    • Portfolio accounting is correct after a round-trip buy→sell.
    • ExecutionRequestEvent rejected when published to wrong channel.
"""

import importlib.util
import datetime
import math
import pathlib
import sys
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------
from schemas import (
    SCHEMA_VERSION,
    ExecutionFilledEvent,
    ExecutionRequestEvent,
    MarketDataEvent,
    SchemaValidationError,
    TradeSignalEvent,
    validate_and_log,
)

# ---------------------------------------------------------------------------
# Service modules
# ---------------------------------------------------------------------------
from risk_engine import RiskEngine
from strategies.sma_crossover import SMACrossover
from core.manager import PortfolioManager
from core.portfolio import VirtualPortfolio
from simulation.slippage import SlippageModel
from risk.validator import OrderValidator

# ---------------------------------------------------------------------------
# Load services/execution/main.py explicitly via importlib.
#
# Multiple services have a `main.py`.  conftest.py inserts each service root
# at sys.path[0] in iteration order, so services/gateway ends up first and a
# plain `import main` would resolve to gateway's main.  We load the execution
# main directly from its file path to avoid this ambiguity, following the same
# pattern used by tests/unit/test_execution_channel_contract.py.
# ---------------------------------------------------------------------------
_EXEC_DIR = pathlib.Path(__file__).parent.parent.parent / "services" / "execution"
_EXEC_MAIN_PATH = _EXEC_DIR / "main.py"

for _mod in ("dotenv", "redis", "redis.asyncio", "alpaca_client", "audit"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["redis"].from_url = MagicMock(return_value=MagicMock())

_exec_dir_str = str(_EXEC_DIR)
if _exec_dir_str not in sys.path:
    sys.path.insert(0, _exec_dir_str)

_spec = importlib.util.spec_from_file_location("execution_main", _EXEC_MAIN_PATH)
_execution_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_execution_main)

simulate_fill = _execution_main.simulate_fill


# ===========================================================================
# Helpers / fixtures
# ===========================================================================

def _make_tick(
    symbol: str = "SPY",
    price: float = 100.0,
    timestamp: str = "2024-01-01T00:00:00",
) -> Dict:
    """Return a minimal valid market data tick dictionary."""
    return {
        "symbol": symbol,
        "price": price,
        "timestamp": timestamp,
        "type": "trade",
        "volume": 1000,
        "schema_version": SCHEMA_VERSION,
    }


def _make_risk_config(**overrides) -> Dict:
    """Return a sensible default risk configuration."""
    base = {
        "MAX_DAILY_LOSS_PCT": 0.03,
        "RISK_PER_TRADE_PCT": 0.01,
        "MAX_CONSECUTIVE_LOSSES": 5,
        "ROLLBACK_MIN_SHARPE": 0.5,
        "ROLLBACK_MIN_ACCURACY": 0.50,
    }
    base.update(overrides)
    return base


async def _trigger_sma_golden_cross(
    strategy: SMACrossover,
) -> Optional[Dict]:
    """
    Feed the strategy enough ticks to produce a golden-cross BUY signal.

    We exploit the crossover logic: if we first fill the window with a
    *declining* price series (fast < slow → potential SHORT state), then
    flip to an *ascending* series long enough to push the fast SMA above
    the slow SMA, the strategy emits a BUY.

    Timestamps are passed as numeric strings (epoch-millisecond style) because
    SMACrossover.on_tick() uses ``int(current_ts)`` internally to compute a
    1-hour forecast offset.  ISO 8601 strings would raise ValueError there.

    Returns the signal dict, or None if none was generated.
    """
    slow = strategy.slow_period
    fast = strategy.fast_period

    # Phase 1 – declining prices so fast SMA < slow SMA (fills the window)
    base = 200.0
    for i in range(slow + 5):
        price = base - i * 0.5          # gently declining: 200 → ~197.5
        tick = _make_tick(price=price, timestamp=str(i))
        await strategy.on_tick(tick)

    # Phase 2 – sharp rising prices to flip fast > slow
    last_price = base - (slow + 5) * 0.5
    signal = None
    for i in range(fast + 5):
        price = last_price + (i + 1) * 3.0   # sharp rise
        tick = _make_tick(price=price, timestamp=str(slow + 5 + i))
        result = await strategy.on_tick(tick)
        if result and result.get("signal") == "BUY":
            signal = result
            break

    return signal


# ===========================================================================
# 1. Schema validation tests
# ===========================================================================

class TestSchemaContracts:
    """Verify that cross-service schema boundaries reject malformed payloads."""

    def test_market_data_valid(self):
        data = _make_tick()
        event = validate_and_log(MarketDataEvent, data, context="e2e:market_data")
        assert event is not None
        assert event.symbol == "SPY"
        assert event.price == 100.0

    def test_market_data_missing_price_rejected(self):
        data = {"symbol": "SPY", "timestamp": "2024-01-01T00:00:00"}
        event = validate_and_log(MarketDataEvent, data, context="e2e")
        assert event is None

    def test_market_data_negative_price_rejected(self):
        data = _make_tick(price=-5.0)
        event = validate_and_log(MarketDataEvent, data, context="e2e")
        assert event is None

    def test_trade_signal_valid(self):
        data = {
            "model_id": "sma_spy",
            "symbol": "SPY",
            "signal": "BUY",
            "confidence": 0.75,
            "timestamp": "2024-01-01T00:00:00",
            "price": 420.0,
            "schema_version": SCHEMA_VERSION,
        }
        event = validate_and_log(TradeSignalEvent, data, context="e2e")
        assert event is not None
        assert event.signal == "BUY"

    def test_trade_signal_invalid_signal_type_rejected(self):
        data = {
            "model_id": "sma_spy",
            "symbol": "SPY",
            "signal": "HOLD_TIGHT",   # invalid
            "confidence": 0.75,
            "timestamp": "2024-01-01T00:00:00",
        }
        event = validate_and_log(TradeSignalEvent, data, context="e2e")
        assert event is None

    def test_trade_signal_confidence_out_of_range_rejected(self):
        data = {
            "model_id": "sma_spy",
            "symbol": "SPY",
            "signal": "BUY",
            "confidence": 1.5,         # > 1.0
            "timestamp": "2024-01-01T00:00:00",
        }
        event = validate_and_log(TradeSignalEvent, data, context="e2e")
        assert event is None

    def test_execution_request_valid(self):
        data = {
            "model_id": "sma_spy",
            "symbol": "SPY",
            "side": "buy",
            "qty": 10,
            "confidence": 0.75,
            "timestamp": "2024-01-01T00:00:00",
            "schema_version": SCHEMA_VERSION,
        }
        event = validate_and_log(ExecutionRequestEvent, data, context="e2e")
        assert event is not None
        assert event.side == "buy"
        assert event.qty == 10

    def test_execution_request_zero_qty_rejected(self):
        data = {
            "model_id": "sma_spy",
            "symbol": "SPY",
            "side": "buy",
            "qty": 0,
            "confidence": 0.75,
            "timestamp": "2024-01-01T00:00:00",
        }
        event = validate_and_log(ExecutionRequestEvent, data, context="e2e")
        assert event is None

    def test_execution_filled_roundtrip(self):
        """ExecutionFilledEvent serialises to dict and deserialises correctly."""
        original = ExecutionFilledEvent(
            id="abc-123",
            order_id="ord-456",
            model_id="sma_spy",
            symbol="SPY",
            side="BUY",
            qty=5,
            price=421.50,
            timestamp="2024-01-01T00:00:00",
            status="FILLED",
            mode="paper",
            slippage=0.21,
            explanation=["golden cross detected"],
            schema_version=SCHEMA_VERSION,
        )
        data = original.to_dict()
        restored = ExecutionFilledEvent.from_dict(data)
        assert restored.id == original.id
        assert restored.price == original.price
        assert restored.slippage == original.slippage
        assert restored.explanation == original.explanation


# ===========================================================================
# 2. Signal generation tests
# ===========================================================================

class TestSignalGeneration:
    """Verify that SMACrossover produces correct signals from price series."""

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_no_signal(self):
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_test"}
        )
        # Only feed 5 ticks (less than slow_period=10)
        for i in range(5):
            result = await strategy.on_tick(_make_tick(price=100.0 + i, timestamp=str(i)))
        assert result is None

    @pytest.mark.asyncio
    async def test_golden_cross_generates_buy_signal(self):
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_test"}
        )
        signal = await _trigger_sma_golden_cross(strategy)
        assert signal is not None, "Expected a BUY signal from golden cross"
        assert signal["signal"] == "BUY"
        assert signal["model_id"] == "sma_test"
        assert signal["symbol"] == "SPY"
        assert 0.0 <= signal["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_signal_contains_required_fields(self):
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_test"}
        )
        signal = await _trigger_sma_golden_cross(strategy)
        assert signal is not None
        required = {"model_id", "symbol", "signal", "confidence", "price", "timestamp"}
        assert required.issubset(signal.keys()), (
            f"Signal missing fields: {required - signal.keys()}"
        )

    @pytest.mark.asyncio
    async def test_signal_validates_as_trade_signal_event(self):
        """Signal dict emitted by SMACrossover must pass TradeSignalEvent schema."""
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_test"}
        )
        signal = await _trigger_sma_golden_cross(strategy)
        assert signal is not None
        signal.setdefault("schema_version", SCHEMA_VERSION)
        event = validate_and_log(TradeSignalEvent, signal, context="e2e:signal_schema")
        assert event is not None, "SMACrossover signal failed TradeSignalEvent validation"


# ===========================================================================
# 3. Risk engine tests (pipeline stage 2)
# ===========================================================================

class TestRiskEnginePipeline:
    """Verify risk engine correctly gates signals and sizes positions."""

    def test_signal_approved_when_engine_healthy(self):
        engine = RiskEngine(_make_risk_config())
        engine.update_account_state(equity=100_000.0, daily_pnl=0.0)
        signal = {
            "model_id": "sma_test",
            "symbol": "SPY",
            "signal": "BUY",
            "confidence": 0.8,
            "price": 420.0,
            "timestamp": "2024-01-01",
        }
        assert engine.validate_signal(signal) is True

    def test_position_size_calculated_correctly(self):
        engine = RiskEngine(_make_risk_config(RISK_PER_TRADE_PCT=0.01))
        engine.update_account_state(equity=100_000.0, daily_pnl=0.0)
        entry = 420.0
        stop_loss = entry * 0.98    # 2% stop
        units = engine.calculate_position_size(entry, stop_loss)
        # risk_amount = 100_000 * 0.01 = 1_000
        # risk_per_share = 420 * 0.02 = 8.4
        # expected_units = floor(1_000 / 8.4) = 119
        assert units == math.floor(1_000.0 / (420.0 * 0.02))

    def test_kill_switch_blocks_signal(self):
        engine = RiskEngine(_make_risk_config())
        engine.is_kill_switch_active = True
        signal = {"model_id": "sma_test", "symbol": "SPY", "signal": "BUY",
                  "confidence": 0.8, "price": 420.0, "timestamp": "2024-01-01"}
        assert engine.validate_signal(signal) is False

    def test_kill_switch_triggered_by_drawdown(self):
        engine = RiskEngine(_make_risk_config(MAX_DAILY_LOSS_PCT=0.03))
        engine.update_account_state(equity=97_000.0, daily_pnl=-3_001.0)
        # starting_equity = 97_000 - (-3_001) = 100_001
        triggered = engine.check_kill_switch()
        assert triggered is True
        assert engine.is_kill_switch_active is True

    def test_kill_switch_triggered_by_consecutive_losses(self):
        engine = RiskEngine(_make_risk_config(MAX_CONSECUTIVE_LOSSES=3))
        engine.update_account_state(equity=99_000.0, daily_pnl=-500.0)
        engine.consecutive_losses = 3
        triggered = engine.check_kill_switch()
        assert triggered is True

    def test_manual_approval_mode_blocks_signal(self):
        engine = RiskEngine(_make_risk_config())
        engine.is_manual_approval_mode = True
        signal = {"model_id": "sma_test", "symbol": "SPY", "signal": "BUY",
                  "confidence": 0.8, "price": 420.0, "timestamp": "2024-01-01"}
        assert engine.validate_signal(signal) is False

    def test_manual_approval_triggered_by_low_sharpe(self):
        engine = RiskEngine(_make_risk_config(ROLLBACK_MIN_SHARPE=0.5))
        # Populate rolling window with consistently negative returns (Sharpe << 0.5)
        for _ in range(10):
            engine.record_prediction(False, -0.05)
        triggered = engine.check_model_performance()
        assert triggered is True
        assert engine.is_manual_approval_mode is True

    def test_manual_approval_triggered_by_low_accuracy(self):
        engine = RiskEngine(_make_risk_config(ROLLBACK_MIN_ACCURACY=0.50))
        # 7 wrong + 3 right = 30% accuracy
        for i in range(10):
            correct = i >= 7
            engine.record_prediction(correct, 0.001 if correct else -0.001)
        triggered = engine.check_model_performance()
        assert triggered is True

    def test_position_size_zero_when_kill_switch_active(self):
        engine = RiskEngine(_make_risk_config())
        engine.update_account_state(equity=100_000.0, daily_pnl=0.0)
        engine.is_kill_switch_active = True
        units = engine.calculate_position_size(420.0, 411.6)
        assert units == 0


# ===========================================================================
# 4. Execution / paper trading tests (pipeline stage 3)
# ===========================================================================

class TestPaperExecution:
    """Verify simulate_fill() produces valid fills and updates the portfolio."""

    def _make_execution_request(
        self,
        model_id: str = "sma_test",
        symbol: str = "SPY",
        side: str = "buy",
        qty: int = 10,
        price: float = 420.0,
    ) -> Dict:
        return {
            "model_id": model_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "confidence": 0.75,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "type": "market",
            "explanation": ["e2e test"],
            "schema_version": SCHEMA_VERSION,
        }

    @pytest.mark.asyncio
    async def test_buy_fill_returned_for_valid_request(self):
        manager = PortfolioManager()
        req = self._make_execution_request(qty=10, price=100.0)
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(req, current_price=100.0, manager=manager)

        assert fill is not None
        assert fill["symbol"] == "SPY"
        assert fill["side"] == "BUY"
        assert fill["qty"] == 10
        assert fill["status"] == "FILLED"
        assert fill["mode"] == "paper"
        assert math.isfinite(fill["price"])
        assert fill["price"] > 0

    @pytest.mark.asyncio
    async def test_fill_event_passes_schema_validation(self):
        manager = PortfolioManager()
        req = self._make_execution_request(qty=5, price=200.0)
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(req, current_price=200.0, manager=manager)

        assert fill is not None
        fill.setdefault("schema_version", SCHEMA_VERSION)
        event = validate_and_log(ExecutionFilledEvent, fill, context="e2e:fill_schema")
        assert event is not None, f"Fill failed ExecutionFilledEvent validation: {fill}"

    @pytest.mark.asyncio
    async def test_zero_qty_returns_no_fill(self):
        manager = PortfolioManager()
        req = self._make_execution_request(qty=0, price=100.0)
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(req, current_price=100.0, manager=manager)

        assert fill is None

    @pytest.mark.asyncio
    async def test_invalid_price_returns_no_fill(self):
        manager = PortfolioManager()
        req = self._make_execution_request(qty=5, price=0.0)
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(req, current_price=0.0, manager=manager)

        assert fill is None

    @pytest.mark.asyncio
    async def test_sell_without_position_returns_no_fill(self):
        manager = PortfolioManager()
        req = self._make_execution_request(side="sell", qty=5, price=100.0)
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(req, current_price=100.0, manager=manager)

        assert fill is None

    @pytest.mark.asyncio
    async def test_buy_decrements_cash(self):
        manager = PortfolioManager()
        portfolio = manager.create_portfolio("sma_test", starting_cash=100_000.0)
        req = self._make_execution_request(qty=10, price=100.0)
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(req, current_price=100.0, manager=manager)

        assert fill is not None
        # Trigger the portfolio ledger update (mirrors what run_paper_execution does)
        manager.on_execution_fill(fill)
        # Cash should have decreased by approximately qty * price
        assert portfolio.cash < 100_000.0


# ===========================================================================
# 5. Full end-to-end pipeline tests
# ===========================================================================

# Risk config for full pipeline tests: RISK_PER_TRADE_PCT must be small enough
# that the resulting position value stays within OrderValidator's 20% concentration
# limit.  position_value ≈ equity * risk_pct / stop_pct (0.02), so we need
# risk_pct < 0.20 * 0.02 = 0.004.  Using 0.003 gives a comfortable margin.
_PIPELINE_RISK_CONFIG = {
    "MAX_DAILY_LOSS_PCT": 0.03,
    "RISK_PER_TRADE_PCT": 0.003,
    "MAX_CONSECUTIVE_LOSSES": 5,
    "ROLLBACK_MIN_SHARPE": 0.5,
    "ROLLBACK_MIN_ACCURACY": 0.50,
}


class TestFullPipeline:
    """
    Test the complete signal → risk → execution chain without any Redis calls.

    Each test manually chains the three pipeline stages:
        1. SMACrossover produces a raw signal dict
        2. RiskEngine validates and sizes the order
        3. simulate_fill() executes the order in paper mode
    """

    def _build_execution_request_from_signal(
        self, signal: Dict, engine: RiskEngine
    ) -> Optional[Dict]:
        """Mirror what risk/main.py does to convert a signal into an execution request."""
        signal_event = validate_and_log(
            TradeSignalEvent, signal, context="e2e:risk:consume"
        )
        if signal_event is None:
            return None

        if not engine.validate_signal(signal):
            return None

        if engine.check_kill_switch():
            return None

        price = signal_event.price
        if price <= 0:
            return None

        stop_loss = price * (0.98 if signal_event.signal == "BUY" else 1.02)
        units = engine.calculate_position_size(price, stop_loss)
        if units <= 0:
            return None

        return ExecutionRequestEvent(
            model_id=signal_event.model_id,
            symbol=signal_event.symbol,
            qty=units,
            side="buy" if signal_event.signal == "BUY" else "sell",
            type="market",
            confidence=signal_event.confidence,
            explanation=signal_event.explanation,
            timestamp=signal_event.timestamp,
            schema_version=SCHEMA_VERSION,
        ).to_dict()

    @pytest.mark.asyncio
    async def test_happy_path_market_tick_to_fill(self):
        """A golden-cross signal flows through risk and arrives as a valid fill."""
        # Stage 1: Signal
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_e2e"}
        )
        signal = await _trigger_sma_golden_cross(strategy)
        assert signal is not None, "Prerequisite: SMA strategy must generate a BUY signal"
        signal.setdefault("schema_version", SCHEMA_VERSION)

        # Stage 2: Risk — use conservative risk_per_trade so position value stays
        # within OrderValidator's 20% concentration limit (≈ equity * 0.003 / 0.02 = 15k)
        engine = RiskEngine(_PIPELINE_RISK_CONFIG)
        engine.update_account_state(equity=100_000.0, daily_pnl=0.0)
        exec_req = self._build_execution_request_from_signal(signal, engine)
        assert exec_req is not None, "Risk engine should approve the signal"
        assert exec_req["side"] == "buy"
        assert exec_req["qty"] > 0

        # Stage 3: Execution
        manager = PortfolioManager()
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(
                exec_req,
                current_price=float(signal["price"]),
                manager=manager,
            )

        assert fill is not None, "Execution should produce a fill"
        assert fill["status"] == "FILLED"
        assert fill["mode"] == "paper"
        assert fill["symbol"] == "SPY"
        assert fill["side"] == "BUY"

        # Validate the fill passes final schema check
        fill.setdefault("schema_version", SCHEMA_VERSION)
        fill_event = validate_and_log(
            ExecutionFilledEvent, fill, context="e2e:pipeline:final"
        )
        assert fill_event is not None

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_pipeline(self):
        """After kill-switch activation no execution request is produced."""
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_e2e"}
        )
        signal = await _trigger_sma_golden_cross(strategy)
        assert signal is not None
        signal.setdefault("schema_version", SCHEMA_VERSION)

        engine = RiskEngine(_PIPELINE_RISK_CONFIG)
        # Simulate 3% daily loss to trigger the kill switch
        engine.update_account_state(equity=97_000.0, daily_pnl=-3_100.0)

        exec_req = self._build_execution_request_from_signal(signal, engine)
        assert exec_req is None, "Kill-switch-active engine must block execution requests"

    @pytest.mark.asyncio
    async def test_manual_approval_mode_blocks_pipeline(self):
        """Signals are suppressed when manual-approval mode is active."""
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_e2e"}
        )
        signal = await _trigger_sma_golden_cross(strategy)
        assert signal is not None
        signal.setdefault("schema_version", SCHEMA_VERSION)

        engine = RiskEngine(_PIPELINE_RISK_CONFIG)
        engine.update_account_state(equity=100_000.0, daily_pnl=0.0)
        engine.is_manual_approval_mode = True

        exec_req = self._build_execution_request_from_signal(signal, engine)
        assert exec_req is None, "Manual-approval-mode engine must not forward signals"

    @pytest.mark.asyncio
    async def test_portfolio_updated_after_fill(self):
        """After a BUY fill the portfolio cash decreases and position is recorded."""
        strategy = SMACrossover(
            {"symbol": "SPY", "fast_period": 5, "slow_period": 10, "model_id": "sma_e2e"}
        )
        signal = await _trigger_sma_golden_cross(strategy)
        assert signal is not None
        signal.setdefault("schema_version", SCHEMA_VERSION)

        engine = RiskEngine(_PIPELINE_RISK_CONFIG)
        engine.update_account_state(equity=100_000.0, daily_pnl=0.0)

        exec_req = self._build_execution_request_from_signal(signal, engine)
        assert exec_req is not None

        manager = PortfolioManager()
        price = float(signal["price"])
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(exec_req, current_price=price, manager=manager)

        assert fill is not None
        # Mirror what run_paper_execution does: apply fill to portfolio ledger
        manager.on_execution_fill(fill)
        portfolio = manager.get_portfolio("sma_e2e")
        assert portfolio is not None
        assert portfolio.cash < 100_000.0
        assert "SPY" in portfolio.positions
        assert portfolio.positions["SPY"]["qty"] > 0

    @pytest.mark.asyncio
    async def test_buy_then_sell_roundtrip(self):
        """A BUY followed by a SELL closes the position and records realized PnL."""
        manager = PortfolioManager()
        portfolio = manager.create_portfolio("roundtrip_model", starting_cash=100_000.0)
        price = 100.0

        # BUY
        buy_req = {
            "model_id": "roundtrip_model",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 50,
            "price": price,
            "confidence": 0.8,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
        }
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            buy_fill = await simulate_fill(buy_req, current_price=price, manager=manager)

        assert buy_fill is not None
        # Apply fill to portfolio ledger (mirrors run_paper_execution)
        manager.on_execution_fill(buy_fill)
        assert "AAPL" in portfolio.positions

        # SELL (price has moved up)
        new_price = 110.0
        sell_req = {
            "model_id": "roundtrip_model",
            "symbol": "AAPL",
            "side": "sell",
            "qty": 50,
            "price": new_price,
            "confidence": 0.8,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
        }
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            sell_fill = await simulate_fill(sell_req, current_price=new_price, manager=manager)

        assert sell_fill is not None
        manager.on_execution_fill(sell_fill)
        assert "AAPL" not in portfolio.positions, "Position should be fully closed"
        # Check trade history records the sell with positive realized PnL
        sell_trades = [t for t in portfolio.history if t["side"] == "sell"]
        assert len(sell_trades) == 1
        assert sell_trades[0]["realized_pnl"] > 0

    @pytest.mark.asyncio
    async def test_execution_rejects_signal_from_wrong_channel(self):
        """
        Confirm that simulate_fill() rejects a *raw* trade_signals payload
        (i.e. a dict that lacks the 'qty' field set by the risk engine).
        """
        raw_signal = {
            "model_id": "sma_e2e",
            "symbol": "SPY",
            "signal": "BUY",          # trade_signals field, not execution_requests
            "confidence": 0.75,
            "price": 420.0,
            "timestamp": "2024-01-01T00:00:00",
            "schema_version": SCHEMA_VERSION,
        }
        # qty is absent → simulate_fill returns None (qty=0 default → guard hits)
        manager = PortfolioManager()
        with patch.object(_execution_main.latency_sim, "delay", new_callable=AsyncMock):
            fill = await simulate_fill(raw_signal, current_price=420.0, manager=manager)

        assert fill is None, (
            "simulate_fill must reject a raw trade_signal payload "
            "(no pre-calculated qty from risk engine)"
        )
