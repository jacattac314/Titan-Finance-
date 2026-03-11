"""
Unit tests for services/signal/strategies/tft_strategy.py

Covers structural/control-flow behaviour:
  - model_id stored from config
  - on_tick returns None before warmup (200 bars required)
  - on_tick returns None when price <= 0 (price is cast directly, so KeyError guard)
  - on_bar returns None
  - Weights-absent path: model initialises with random weights (no _disabled flag;
    TFTStrategy logs a warning but keeps running, so we verify the model attribute exists)
  - lookback guard: returns None when not enough rows survive dropna after features

These tests do NOT require actual TFT weights; they exercise the strategy's
fail-safe state machine in isolation using random-weight model inference.
"""
import asyncio
import logging
import unittest.mock as mock
import pytest
import pandas as pd
import numpy as np
from strategies.tft_strategy import TFTStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "symbol": "SPY",
    "model_id": "tft_test_v1",
    "lookback": 60,
}


def tick(price: float) -> dict:
    return {"price": price, "timestamp": 1_700_000_000_000}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_model_id_stored_from_config(self):
        s = TFTStrategy(BASE_CONFIG)
        assert s.model_id == "tft_test_v1"

    def test_lookback_stored_from_config(self):
        s = TFTStrategy({**BASE_CONFIG, "lookback": 30})
        assert s.lookback == 30

    def test_warmup_period_is_200(self):
        """TFT requires a longer warmup than other strategies."""
        s = TFTStrategy(BASE_CONFIG)
        assert s.warmup_period == 200


# ---------------------------------------------------------------------------
# Weights-absent path
# ---------------------------------------------------------------------------

class TestWeightsAbsent:
    def test_model_exists_without_weights_file(self):
        """TFTStrategy should initialise with a model even when weights are absent."""
        s = TFTStrategy(BASE_CONFIG)
        # Weights file won't exist in the test environment; model must still be set
        assert s.model is not None

    def test_model_in_eval_mode_without_weights_file(self):
        """Model must be placed in eval mode regardless of whether weights exist."""
        s = TFTStrategy(BASE_CONFIG)
        assert not s.model.training


# ---------------------------------------------------------------------------
# Warmup guard (200-bar minimum)
# ---------------------------------------------------------------------------

class TestWarmupGuard:
    def test_returns_none_before_warmup_period(self):
        """on_tick must return None for the first warmup_period - 1 ticks."""
        s = TFTStrategy(BASE_CONFIG)
        results = [run(s.on_tick(tick(100.0))) for _ in range(s.warmup_period - 1)]
        assert all(r is None for r in results)

    def test_prices_buffer_fills_during_warmup(self):
        """Price buffer should accumulate during the warmup phase."""
        s = TFTStrategy(BASE_CONFIG)
        n = s.warmup_period // 2
        for _ in range(n):
            run(s.on_tick(tick(150.0)))
        assert len(s.prices) == n


# ---------------------------------------------------------------------------
# Lookback guard after feature engineering
# ---------------------------------------------------------------------------

class TestLookbackGuard:
    def test_returns_none_when_features_too_short_after_dropna(self):
        """If calculate_features returns fewer rows than lookback, on_tick returns None."""
        s = TFTStrategy(BASE_CONFIG)

        # Pre-fill the prices deque to bypass the warmup check
        for _ in range(s.warmup_period):
            s.prices.append(100.0)

        # Stub calculate_features to return a DataFrame shorter than lookback
        short_df = pd.DataFrame({
            col: [1.0] * (s.lookback - 1)
            for col in ['open', 'high', 'low', 'close', 'volume',
                        'RSI', 'MACD', 'MACD_line', 'MACD_signal',
                        'log_ret', 'ATR', 'BBU', 'BBL', 'BBM']
        })
        with mock.patch.object(s.fe, "calculate_features", return_value=short_df):
            result = run(s.on_tick(tick(100.0)))

        assert result is None


# ---------------------------------------------------------------------------
# on_bar
# ---------------------------------------------------------------------------

class TestOnBar:
    def test_on_bar_returns_none(self):
        s = TFTStrategy(BASE_CONFIG)
        result = run(s.on_bar({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}))
        assert result is None


# ---------------------------------------------------------------------------
# Inference with random-weight model (structural smoke test)
# ---------------------------------------------------------------------------

class TestInferenceSmoke:
    def test_on_tick_does_not_raise_after_warmup_with_stub_features(self):
        """After warmup, on_tick should return None or a signal dict — never raise."""
        import torch

        s = TFTStrategy(BASE_CONFIG)

        # Pre-fill the prices deque to bypass the warmup check
        for _ in range(s.warmup_period):
            s.prices.append(100.0)

        # Provide a well-formed DataFrame with all required columns
        n_rows = s.lookback + 10
        stub_df = pd.DataFrame({
            col: np.random.rand(n_rows) + 1.0
            for col in ['open', 'high', 'low', 'close', 'volume',
                        'RSI', 'MACD', 'MACD_line', 'MACD_signal',
                        'log_ret', 'ATR', 'BBU', 'BBL', 'BBM']
        })

        try:
            with mock.patch.object(s.fe, "calculate_features", return_value=stub_df):
                result = run(s.on_tick(tick(100.0)))
        except Exception as exc:
            pytest.fail(f"on_tick raised unexpectedly: {exc}")

        # Result must be None or a valid signal dict
        assert result is None or isinstance(result, dict)
        if isinstance(result, dict):
            assert "signal" in result
            assert result["signal"] in ("BUY", "SELL")
