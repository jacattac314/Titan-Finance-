"""
Unit tests for services/signal/strategies/tft_strategy.py

TFTStrategy runs a Transformer-based forecaster on a rolling tick buffer.
Tests mirror the LSTM strategy structure: warmup guard, no-exception
contract for full-buffer inference, and on_bar() delegation.
"""
import asyncio
import math
import pytest
from strategies.tft_strategy import TFTStrategy
from collections import deque


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_strategy(warmup: int = 200, lookback: int = 60) -> TFTStrategy:
    s = TFTStrategy({"symbol": "SPY", "model_id": "test_tft", "lookback": lookback})
    s.warmup_period = warmup
    s.prices = deque(maxlen=warmup)
    return s


def make_tick(price: float, i: int = 0) -> dict:
    return {"price": price, "timestamp": i * 1_000_000_000}


def oscillating_price(i: int, base: float = 100.0) -> float:
    return base + math.sin(i * 0.15) * 5.0 + i * 0.01


# ---------------------------------------------------------------------------
# Warmup guard
# ---------------------------------------------------------------------------

class TestWarmupGuard:
    def test_returns_none_before_warmup_complete(self):
        s = make_strategy(warmup=20)
        for i in range(15):
            result = run(s.on_tick(make_tick(100.0 + i * 0.1, i)))
        assert result is None

    def test_still_none_one_tick_before_warmup(self):
        s = make_strategy(warmup=10)
        for i in range(9):
            result = run(s.on_tick(make_tick(oscillating_price(i), i)))
        assert result is None


# ---------------------------------------------------------------------------
# Full-buffer behaviour — no exception
# ---------------------------------------------------------------------------

class TestFullBufferNoException:
    def test_no_exception_after_warmup(self):
        s = make_strategy(warmup=100, lookback=30)
        result = None
        for i in range(100):
            result = run(s.on_tick(make_tick(oscillating_price(i), i)))
        if result is not None:
            assert result["symbol"] == "SPY"
            assert result["signal"] in ("BUY", "SELL")
            assert 0.0 <= result["confidence"] <= 1.0

    def test_returns_none_or_signal_dict(self):
        s = make_strategy(warmup=100, lookback=30)
        for i in range(100):
            result = run(s.on_tick(make_tick(oscillating_price(i), i)))
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# on_bar delegation
# ---------------------------------------------------------------------------

class TestOnBar:
    def test_on_bar_returns_none_before_warmup(self):
        s = make_strategy(warmup=20)
        bar = {"open": 100.0, "high": 101.0, "low": 99.0,
               "close": 100.5, "volume": 1000, "timestamp": 0}
        result = run(s.on_bar(bar))
        assert result is None

    def test_on_bar_does_not_raise(self):
        s = make_strategy(warmup=20)
        bar = {"open": 100.0, "high": 101.0, "low": 99.0,
               "close": 100.5, "volume": 1000, "timestamp": 0}
        try:
            run(s.on_bar(bar))
        except Exception as exc:
            pytest.fail(f"on_bar raised unexpectedly: {exc}")

    def test_on_bar_advances_price_buffer(self):
        s = make_strategy(warmup=20)
        initial_len = len(s.prices)
        run(s.on_bar({"close": 101.0, "timestamp": 0}))
        assert len(s.prices) == initial_len + 1
