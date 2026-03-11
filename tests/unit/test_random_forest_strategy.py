"""
Unit tests for services/signal/strategies/random_forest_strategy.py

Covers structural/control-flow behaviour:
  - model_id stored from config
  - on_tick returns None before warmup (insufficient bars)
  - on_tick returns None when price <= 0
  - on_bar returns None
  - model_ready guard: returns None until enough bars are accumulated for fitting

These tests do NOT require trained model weights; they exercise the strategy's
fail-safe state machine in isolation.
"""
import asyncio
import logging
import unittest.mock as mock
import pytest
import pandas as pd
from strategies.random_forest_strategy import RandomForestStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "symbol": "SPY",
    "model_id": "rf_test_v1",
    "min_bars": 100,
    "confidence_threshold": 0.62,
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
        s = RandomForestStrategy(BASE_CONFIG)
        assert s.model_id == "rf_test_v1"

    def test_min_bars_stored_from_config(self):
        s = RandomForestStrategy({**BASE_CONFIG, "min_bars": 60})
        assert s.min_bars == 60

    def test_confidence_threshold_stored_from_config(self):
        s = RandomForestStrategy({**BASE_CONFIG, "confidence_threshold": 0.70})
        assert s.confidence_threshold == pytest.approx(0.70)


# ---------------------------------------------------------------------------
# Warmup guard
# ---------------------------------------------------------------------------

class TestWarmupGuard:
    def test_returns_none_before_min_bars(self):
        """on_tick must return None while fewer than min_bars bars are buffered."""
        s = RandomForestStrategy(BASE_CONFIG)
        results = [run(s.on_tick(tick(100.0))) for _ in range(s.min_bars - 1)]
        assert all(r is None for r in results)

    def test_model_not_ready_after_insufficient_bars(self):
        """model_ready must be False when not enough bars have been accumulated."""
        s = RandomForestStrategy(BASE_CONFIG)
        for _ in range(s.min_bars - 1):
            run(s.on_tick(tick(100.0)))
        assert s.model_ready is False


# ---------------------------------------------------------------------------
# Zero / negative price guard
# ---------------------------------------------------------------------------

class TestPriceGuard:
    def test_zero_price_returns_none(self):
        s = RandomForestStrategy(BASE_CONFIG)
        assert run(s.on_tick(tick(0.0))) is None

    def test_negative_price_returns_none(self):
        s = RandomForestStrategy(BASE_CONFIG)
        assert run(s.on_tick(tick(-5.0))) is None

    def test_zero_price_does_not_append_bar(self):
        """A zero-price tick must not pollute the price buffer."""
        s = RandomForestStrategy(BASE_CONFIG)
        run(s.on_tick(tick(0.0)))
        assert len(s.bars) == 0


# ---------------------------------------------------------------------------
# model_ready guard — returns None when _fit_model fails silently
# ---------------------------------------------------------------------------

class TestModelReadyGuard:
    def test_returns_none_when_model_not_ready_after_min_bars(self):
        """If _fit_model cannot train (e.g. stub features), on_tick returns None."""
        s = RandomForestStrategy(BASE_CONFIG)

        # Stub calculate_features to return an empty DataFrame so _fit_model bails out
        empty_df = pd.DataFrame()
        with mock.patch.object(s.fe, "calculate_features", return_value=empty_df):
            for _ in range(s.min_bars + 5):
                result = run(s.on_tick(tick(100.0)))

        assert s.model_ready is False
        assert result is None


# ---------------------------------------------------------------------------
# on_bar
# ---------------------------------------------------------------------------

class TestOnBar:
    def test_on_bar_returns_none(self):
        s = RandomForestStrategy(BASE_CONFIG)
        result = run(s.on_bar({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}))
        assert result is None


# ---------------------------------------------------------------------------
# RandomForest-specific: model structure
# ---------------------------------------------------------------------------

class TestModelStructure:
    def test_model_has_expected_estimators(self):
        """RandomForestClassifier should be configured with n_estimators=200."""
        s = RandomForestStrategy(BASE_CONFIG)
        assert s.model.n_estimators == 200

    def test_model_has_max_depth_five(self):
        s = RandomForestStrategy(BASE_CONFIG)
        assert s.model.max_depth == 5
