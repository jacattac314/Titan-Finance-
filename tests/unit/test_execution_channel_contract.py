"""
Contract tests for the execution service's risk-gated channel wiring.

These tests enforce two invariants:

1. simulate_fill() only produces fills for execution_requests payloads
   (risk-approved, with pre-calculated qty and lowercase side).
   A raw trade_signals payload must NEVER produce a fill.

2. run_paper_execution() and run_live_execution() subscribe to
   "execution_requests", never directly to "trade_signals".

Together these tests will fail immediately if the risk-gating bypass is
re-introduced, giving CI a deterministic signal contract regression check.
"""
import importlib.util
import inspect
import pathlib
import re
import sys
from unittest.mock import MagicMock

from core.manager import PortfolioManager

# ---------------------------------------------------------------------------
# Load services/execution/main.py explicitly.
#
# conftest.py puts services/gateway first in sys.path (it iterates the list and
# calls sys.path.insert(0, ...) for each root, so the last root ends up at index
# 0).  A plain `import main` would therefore pick up services/gateway/main.py
# instead of services/execution/main.py.  We bypass that by loading the file
# directly via importlib and mocking heavy external deps first.
# ---------------------------------------------------------------------------

_EXEC_DIR = pathlib.Path(__file__).parent.parent.parent / "services" / "execution"
_EXEC_MAIN_PATH = _EXEC_DIR / "main.py"

# Pre-register mocks for external packages that are unavailable in this test
# environment.  load_dotenv() and redis are called at module import time in
# main.py; alpaca_client/audit need mocking to avoid ImportError.
for _mod in ("dotenv", "redis", "redis.asyncio", "alpaca_client", "audit"):
    sys.modules.setdefault(_mod, MagicMock())

# Make MagicMock.from_url() return a further MagicMock (called in main())
sys.modules["redis"].from_url = MagicMock(return_value=MagicMock())

# Ensure services/execution is importable for sub-modules (core, simulation, risk)
_exec_dir_str = str(_EXEC_DIR)
if _exec_dir_str not in sys.path:
    sys.path.insert(0, _exec_dir_str)

spec = importlib.util.spec_from_file_location("execution_main", _EXEC_MAIN_PATH)
execution_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(execution_main)

simulate_fill = execution_main.simulate_fill

# Read source once for the channel-subscription contract tests.
_MAIN_SOURCE = _EXEC_MAIN_PATH.read_text()


# ---------------------------------------------------------------------------
# Helpers — payload builders
# ---------------------------------------------------------------------------

def _execution_request(
    model_id: str = "sma_spy_v1",
    symbol: str = "SPY",
    side: str = "buy",   # RiskGuardian publishes lowercase "buy"/"sell"
    qty: int = 10,
    price: float = 450.0,
) -> dict:
    """Mimics the payload RiskGuardian publishes to execution_requests."""
    return {
        "model_id": model_id,
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": "market",
        "confidence": 0.75,
        "explanation": ["rsi: 0.42", "macd: 0.18"],
        "timestamp": "2024-01-01T14:30:00Z",
        # price intentionally absent to exercise current_price fallback
    }


def _trade_signal(
    model_id: str = "sma_spy_v1",
    symbol: str = "SPY",
    signal: str = "BUY",
    price: float = 450.0,
) -> dict:
    """Mimics the payload the Signal service publishes to trade_signals.
    Key differences from execution_requests: uses 'signal' not 'side',
    and has NO 'qty' field.  This format must never produce a fill."""
    return {
        "model_id": model_id,
        "symbol": symbol,
        "signal": signal,   # 'signal', not 'side'
        "confidence": 0.8,
        "price": price,
        "timestamp": "2024-01-01T14:30:00Z",
        "explanation": [],
        # No 'qty' — Signal service never pre-sizes positions
    }


# ---------------------------------------------------------------------------
# Part 1: simulate_fill payload format contract
# ---------------------------------------------------------------------------

class TestSimulateFillAcceptsExecutionRequests:
    """simulate_fill must succeed for well-formed execution_requests payloads."""

    async def test_buy_produces_fill(self):
        manager = PortfolioManager()
        req = _execution_request(side="buy", qty=5, price=450.0)
        fill = await simulate_fill(req, current_price=450.0, manager=manager)
        assert fill is not None, "Expected a fill for a valid execution_request"
        assert fill["symbol"] == "SPY"
        assert fill["side"] == "BUY"
        assert fill["qty"] == 5
        assert fill["status"] == "FILLED"
        assert fill["mode"] == "paper"

    async def test_lowercase_side_is_normalised_to_uppercase(self):
        """Risk publishes 'buy'/'sell'; simulate_fill must normalise to uppercase."""
        manager = PortfolioManager()
        req = _execution_request(side="buy", qty=3, price=200.0)
        fill = await simulate_fill(req, current_price=200.0, manager=manager)
        assert fill is not None
        assert fill["side"] == "BUY"

    async def test_falls_back_to_current_price_when_request_omits_price(self):
        """execution_requests may omit price; the current market price is used."""
        manager = PortfolioManager()
        req = _execution_request(side="buy", qty=2)
        req.pop("price", None)
        fill = await simulate_fill(req, current_price=300.0, manager=manager)
        assert fill is not None
        # Slippage shifts price slightly; stay within a realistic bound.
        assert abs(fill["price"] - 300.0) < 10.0

    async def test_fill_carries_required_contract_fields(self):
        """Fill event must include all fields expected by dashboard and risk service."""
        manager = PortfolioManager()
        req = _execution_request(side="buy", qty=4, price=100.0)
        fill = await simulate_fill(req, current_price=100.0, manager=manager)
        assert fill is not None
        required = {
            "id", "order_id", "model_id", "symbol", "side",
            "qty", "price", "timestamp", "status", "mode",
            "slippage", "explanation",
        }
        missing = required - fill.keys()
        assert not missing, f"Fill event missing required fields: {missing}"


class TestSimulateFillRejectsTradeSignals:
    """simulate_fill must return None for raw trade_signals payloads.

    A raw signal uses 'signal' instead of 'side' and carries no 'qty'.
    Both absences must individually force simulate_fill to return None,
    so a direct trade_signals → execution bypass can never work.
    """

    async def test_raw_signal_payload_is_rejected(self):
        """trade_signals format ('signal' key, no 'qty') must never produce a fill."""
        manager = PortfolioManager()
        raw = _trade_signal(signal="BUY", price=450.0)
        fill = await simulate_fill(raw, current_price=450.0, manager=manager)
        assert fill is None, (
            "simulate_fill MUST return None for a raw trade_signals payload. "
            "Only risk-approved execution_requests should ever produce fills."
        )

    async def test_zero_qty_is_rejected(self):
        manager = PortfolioManager()
        req = _execution_request(side="buy", qty=0)
        fill = await simulate_fill(req, current_price=450.0, manager=manager)
        assert fill is None

    async def test_missing_side_is_rejected(self):
        manager = PortfolioManager()
        req = {"model_id": "m1", "symbol": "SPY", "qty": 5, "confidence": 0.9}
        fill = await simulate_fill(req, current_price=450.0, manager=manager)
        assert fill is None

    async def test_hold_side_is_rejected(self):
        """'HOLD' is not a valid execution side — only BUY and SELL are actionable."""
        manager = PortfolioManager()
        req = _execution_request(side="hold", qty=5, price=450.0)
        fill = await simulate_fill(req, current_price=450.0, manager=manager)
        assert fill is None


# ---------------------------------------------------------------------------
# Part 2: Channel subscription source contract
# ---------------------------------------------------------------------------

class TestChannelSubscriptionContract:
    """Assert subscribe() calls in both execution loops use the correct channels.

    Source inspection means any refactor that reverts the channel name fails CI
    before the service even boots.
    """

    def _subscribe_args(self, fn_name: str) -> list:
        """Return argument strings from every pubsub.subscribe(...) call in fn."""
        # Extract only the relevant function's source from the full module source
        src = inspect.getsource(getattr(execution_main, fn_name))
        return re.findall(r'subscribe\(([^)]+)\)', src)

    def test_paper_loop_subscribes_to_execution_requests(self):
        src = inspect.getsource(execution_main.run_paper_execution)
        assert "execution_requests" in src, (
            "run_paper_execution must subscribe to 'execution_requests'"
        )

    def test_paper_loop_does_not_subscribe_to_trade_signals(self):
        for call in self._subscribe_args("run_paper_execution"):
            assert "trade_signals" not in call, (
                f"run_paper_execution must NOT subscribe to 'trade_signals'. "
                f"Found in subscribe(): {call}"
            )

    def test_paper_loop_channel_handler_checks_execution_requests(self):
        src = inspect.getsource(execution_main.run_paper_execution)
        branch_channels = re.findall(r'channel\s*==\s*["\']([^"\']+)["\']', src)
        assert "execution_requests" in branch_channels, (
            "run_paper_execution must have an elif branch for 'execution_requests'"
        )
        assert "trade_signals" not in branch_channels, (
            f"run_paper_execution must not branch on 'trade_signals'. "
            f"Found: {branch_channels}"
        )

    def test_live_loop_subscribes_to_execution_requests(self):
        src = inspect.getsource(execution_main.run_live_execution)
        assert "execution_requests" in src, (
            "run_live_execution must subscribe to 'execution_requests'"
        )

    def test_live_loop_does_not_subscribe_to_trade_signals(self):
        for call in self._subscribe_args("run_live_execution"):
            assert "trade_signals" not in call, (
                f"run_live_execution must NOT subscribe to 'trade_signals'. "
                f"Found in subscribe(): {call}"
            )
