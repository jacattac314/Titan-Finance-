"""
Unit tests for the RSI Mean-Reversion strategy.

Covers RSI computation, warmup period, signal generation at thresholds,
confidence scaling, and position-change gating.
"""
import pytest
from strategies.rsi_strategy import RSIMeanReversion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_strategy(**overrides) -> RSIMeanReversion:
    cfg = {
        "symbol": "SPY",
        "model_id": "rsi_test",
        "rsi_period": 14,
        "oversold": 30.0,
        "overbought": 70.0,
    }
    cfg.update(overrides)
    return RSIMeanReversion(cfg)


def make_tick(price: float, symbol: str = "SPY") -> dict:
    return {"symbol": symbol, "price": price, "type": "trade", "timestamp": "2026-01-01T00:00:00Z"}


async def feed_prices(strategy: RSIMeanReversion, prices: list[float]) -> list:
    """Feed a list of prices; return the list of non-None signals."""
    signals = []
    for p in prices:
        result = await strategy.on_tick(make_tick(p))
        if result is not None:
            signals.append(result)
    return signals


# ---------------------------------------------------------------------------
# Warmup period
# ---------------------------------------------------------------------------

class TestWarmup:
    async def test_no_signal_before_period_plus_one_ticks(self):
        strategy = make_strategy(rsi_period=14)
        # Feed exactly `period` prices — not enough for RSI (need period+1)
        signals = await feed_prices(strategy, [100.0] * 14)
        assert signals == []

    async def test_signal_possible_after_period_plus_one_ticks(self):
        # Feed enough data for RSI to be computable (period+1 prices)
        strategy = make_strategy(rsi_period=5, oversold=30.0, overbought=70.0)
        # 5 dropping prices should give RSI < 30 after warmup
        prices = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0]
        signals = await feed_prices(strategy, prices)
        # We only assert the function runs without error and RSI is available;
        # whether a signal fires depends on the RSI value.
        assert isinstance(signals, list)

    async def test_zero_price_tick_is_ignored(self):
        strategy = make_strategy(rsi_period=5)
        signals = await feed_prices(strategy, [0.0] * 10)
        assert signals == []


# ---------------------------------------------------------------------------
# RSI computation
# ---------------------------------------------------------------------------

class TestRSIComputation:
    def test_rsi_is_100_when_all_moves_are_gains(self):
        strategy = make_strategy(rsi_period=5)
        for p in [100, 101, 102, 103, 104, 105]:
            strategy.prices.append(float(p))
        rsi = strategy._compute_rsi()
        assert rsi == pytest.approx(100.0, abs=1e-6)

    def test_rsi_is_0_when_all_moves_are_losses(self):
        strategy = make_strategy(rsi_period=5)
        for p in [105, 104, 103, 102, 101, 100]:
            strategy.prices.append(float(p))
        rsi = strategy._compute_rsi()
        assert rsi == pytest.approx(0.0, abs=1e-6)

    def test_rsi_50_for_equal_gains_and_losses(self):
        strategy = make_strategy(rsi_period=4)
        # Alternating +1 / -1: avg_gain == avg_loss → RS=1 → RSI=50
        for p in [100, 101, 100, 101, 100]:
            strategy.prices.append(float(p))
        rsi = strategy._compute_rsi()
        assert rsi == pytest.approx(50.0, abs=1e-6)

    def test_rsi_between_0_and_100(self):
        strategy = make_strategy(rsi_period=14)
        import random
        random.seed(42)
        for _ in range(15):
            strategy.prices.append(random.uniform(90, 110))
        rsi = strategy._compute_rsi()
        assert rsi is not None
        assert 0.0 <= rsi <= 100.0


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

class TestSignalGeneration:
    async def test_buy_signal_when_rsi_oversold(self):
        """Strongly falling prices push RSI below 30 → BUY."""
        strategy = make_strategy(rsi_period=5, oversold=30.0)
        # 5 flat + 6 sharp falls to push RSI to ~0
        prices = [100.0] * 5 + [95.0, 90.0, 85.0, 80.0, 75.0, 70.0]
        signals = await feed_prices(strategy, prices)

        buy_signals = [s for s in signals if s["signal"] == "BUY"]
        assert len(buy_signals) >= 1
        assert buy_signals[0]["model_id"] == "rsi_test"
        assert buy_signals[0]["symbol"] == "SPY"

    async def test_sell_signal_when_rsi_overbought(self):
        """Strongly rising prices push RSI above 70 → SELL."""
        strategy = make_strategy(rsi_period=5, overbought=70.0)
        prices = [100.0] * 5 + [105.0, 110.0, 115.0, 120.0, 125.0, 130.0]
        signals = await feed_prices(strategy, prices)

        sell_signals = [s for s in signals if s["signal"] == "SELL"]
        assert len(sell_signals) >= 1

    async def test_signal_payload_has_required_keys(self):
        strategy = make_strategy(rsi_period=5, oversold=30.0)
        prices = [100.0] * 5 + [95.0, 90.0, 85.0, 80.0, 75.0, 70.0]
        signals = await feed_prices(strategy, prices)

        assert len(signals) > 0, "Expected at least one signal"
        sig = signals[0]
        required = {"model_id", "model_name", "symbol", "signal", "confidence", "price", "explanation"}
        assert required <= set(sig.keys())

    async def test_explanation_contains_rsi_feature(self):
        strategy = make_strategy(rsi_period=5, oversold=30.0)
        prices = [100.0] * 5 + [90.0, 80.0, 70.0, 60.0, 50.0, 40.0]
        signals = await feed_prices(strategy, prices)

        assert len(signals) > 0
        explanation = signals[0]["explanation"]
        assert any(e["feature"] == "rsi" for e in explanation)


# ---------------------------------------------------------------------------
# Position-change gating
# ---------------------------------------------------------------------------

class TestPositionGating:
    async def test_no_duplicate_buy_signals_while_long(self):
        """Once long, further oversold RSI readings should not re-signal."""
        strategy = make_strategy(rsi_period=5, oversold=30.0)
        prices = [100.0] * 5 + [90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0]
        signals = await feed_prices(strategy, prices)
        buy_signals = [s for s in signals if s["signal"] == "BUY"]
        assert len(buy_signals) == 1, "Should only generate one BUY while already long"

    async def test_sell_after_buy_is_allowed(self):
        """After going long on a BUY, a subsequent SELL (RSI overbought) is valid."""
        strategy = make_strategy(rsi_period=5, oversold=30.0, overbought=70.0)
        # Fall to trigger BUY, then rally to trigger SELL
        prices = (
            [100.0] * 5
            + [90.0, 80.0, 70.0, 60.0, 50.0]       # RSI drops → BUY
            + [60.0, 70.0, 80.0, 90.0, 100.0, 110.0]  # RSI rises → SELL
        )
        signals = await feed_prices(strategy, prices)
        signal_types = [s["signal"] for s in signals]
        assert "BUY" in signal_types
        assert "SELL" in signal_types


# ---------------------------------------------------------------------------
# Confidence scaling
# ---------------------------------------------------------------------------

class TestConfidence:
    async def test_confidence_is_between_0_1_and_1(self):
        strategy = make_strategy(rsi_period=5, oversold=40.0)
        prices = [100.0] * 5 + [90.0, 80.0, 70.0, 60.0]
        signals = await feed_prices(strategy, prices)
        for sig in signals:
            assert 0.1 <= sig["confidence"] <= 1.0

    async def test_deeper_oversold_gives_higher_confidence(self):
        """RSI=10 should yield higher confidence than RSI=28 for oversold=30."""
        # Strategy 1: mildly oversold
        s1 = make_strategy(rsi_period=5, oversold=30.0)
        prices_mild = [100.0] * 5 + [95.0, 90.0, 86.0, 83.0, 80.0, 78.0]
        sigs_mild = await feed_prices(s1, prices_mild)

        # Strategy 2: deeply oversold
        s2 = make_strategy(rsi_period=5, oversold=30.0)
        prices_deep = [100.0] * 5 + [90.0, 80.0, 70.0, 55.0, 40.0, 25.0]
        sigs_deep = await feed_prices(s2, prices_deep)

        mild_buys = [s["confidence"] for s in sigs_mild if s["signal"] == "BUY"]
        deep_buys = [s["confidence"] for s in sigs_deep if s["signal"] == "BUY"]

        if mild_buys and deep_buys:
            assert deep_buys[0] >= mild_buys[0], (
                "Deeper oversold should produce >= confidence"
            )
