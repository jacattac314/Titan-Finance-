"""
Unit tests for services/signal/strategies/sma_crossover.py

SMACrossover emits BUY on a golden cross (fast SMA > slow SMA) and SELL on a
death cross.  Duplicate signal suppression and the warmup guard (not enough
ticks) must also be verified.
"""
import asyncio
import pytest
from strategies.sma_crossover import SMACrossover


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAST = 5
SLOW = 10

BASE_CONFIG = {
    "symbol": "AAPL",
    "model_id": "sma-test",
    "fast_period": FAST,
    "slow_period": SLOW,
}


def make_strategy(**overrides) -> SMACrossover:
    config = {**BASE_CONFIG, **overrides}
    return SMACrossover(config)


def tick(price: float) -> dict:
    return {"price": price, "timestamp": "2024-01-01T00:00:00"}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def feed_ticks(strategy, prices):
    """Feed a list of prices and return the last signal (or None)."""
    result = None
    for p in prices:
        result = await strategy.on_tick(tick(p))
    return result


# ---------------------------------------------------------------------------
# Warmup guard
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_returns_none_before_slow_period_ticks(self):
        s = make_strategy()
        # Feed SLOW - 1 ticks — not enough to compute slow SMA
        signals = [run(s.on_tick(tick(100.0))) for _ in range(SLOW - 1)]
        assert all(sig is None for sig in signals)

    def test_zero_price_tick_returns_none(self):
        s = make_strategy()
        assert run(s.on_tick(tick(0.0))) is None

    def test_negative_price_tick_returns_none(self):
        s = make_strategy()
        assert run(s.on_tick(tick(-5.0))) is None


# ---------------------------------------------------------------------------
# Golden cross → BUY
# ---------------------------------------------------------------------------

class TestGoldenCross:
    def test_emits_buy_signal_on_golden_cross(self):
        s = make_strategy()
        # Establish a downtrend (fast < slow), then flip upward
        # slow_period=10, fast_period=5
        # Fill deque with 10 falling prices so slow SMA > fast SMA
        falling = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0]
        for p in falling:
            run(s.on_tick(tick(p)))
        # Now flood with rising prices so fast SMA crosses above slow SMA
        rising = [110.0, 115.0, 120.0, 125.0, 130.0]
        sig = None
        for p in rising:
            sig = run(s.on_tick(tick(p)))
            if sig is not None:
                break
        assert sig is not None
        assert sig["signal"] == "BUY"
        assert sig["symbol"] == "AAPL"
        assert sig["model_id"] == "sma-test"

    def test_buy_signal_contains_required_fields(self):
        s = make_strategy()
        falling = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0]
        for p in falling:
            run(s.on_tick(tick(p)))
        rising = [110.0, 115.0, 120.0, 125.0, 130.0]
        sig = None
        for p in rising:
            sig = run(s.on_tick(tick(p)))
            if sig is not None:
                break
        assert sig is not None
        for field in ("model_id", "model_name", "symbol", "signal", "confidence", "price"):
            assert field in sig, f"Missing field '{field}' in signal"


# ---------------------------------------------------------------------------
# Death cross → SELL
# ---------------------------------------------------------------------------

class TestDeathCross:
    def test_emits_sell_signal_on_death_cross(self):
        s = make_strategy()
        # Establish an uptrend first (fast > slow)
        rising = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        for p in rising:
            run(s.on_tick(tick(p)))
        # Drive fast SMA down below slow SMA
        falling = [80.0, 75.0, 70.0, 65.0, 60.0]
        sig = None
        for p in falling:
            sig = run(s.on_tick(tick(p)))
            if sig is not None:
                break
        assert sig is not None
        assert sig["signal"] == "SELL"


# ---------------------------------------------------------------------------
# Duplicate signal suppression
# ---------------------------------------------------------------------------

class TestDuplicateSuppression:
    def test_no_duplicate_buy_when_already_long(self):
        s = make_strategy()
        # Get to LONG state
        falling = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0]
        for p in falling:
            run(s.on_tick(tick(p)))
        rising = [110.0, 115.0, 120.0, 125.0, 130.0]
        signals = []
        for p in rising:
            sig = run(s.on_tick(tick(p)))
            if sig is not None:
                signals.append(sig)
        buy_count = sum(1 for s_ in signals if s_["signal"] == "BUY")
        assert buy_count == 1, f"Expected exactly 1 BUY but got {buy_count}"

    def test_no_duplicate_sell_when_already_short(self):
        s = make_strategy()
        # Get to SHORT state via a death cross
        rising = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        for p in rising:
            run(s.on_tick(tick(p)))
        falling = [80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0, 45.0]
        signals = []
        for p in falling:
            sig = run(s.on_tick(tick(p)))
            if sig is not None:
                signals.append(sig)
        sell_count = sum(1 for s_ in signals if s_["signal"] == "SELL")
        assert sell_count == 1, f"Expected exactly 1 SELL but got {sell_count}"


# ---------------------------------------------------------------------------
# on_bar always returns None (not implemented yet)
# ---------------------------------------------------------------------------

class TestOnBar:
    def test_on_bar_returns_none(self):
        s = make_strategy()
        result = run(s.on_bar({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}))
        assert result is None
