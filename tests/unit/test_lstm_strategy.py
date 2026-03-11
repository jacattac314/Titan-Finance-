"""
Unit tests for services/signal/strategies/lstm_strategy.py

Covers the audit fixes:
  - Feature validation: missing columns → error log + None return (no crash).
  - Inference error handling: RuntimeError during torch inference → None return.
  - Warmup guard: returns None before enough ticks.
  - model_id stored from config.

These tests use the uninitialized (random weights) LSTMModel, which is
acceptable for structural/control-flow tests.
"""
import asyncio
import logging
import unittest.mock as mock
import pytest
import torch
from strategies.lstm_strategy import LSTMStrategy, _REQUIRED_FEATURES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "symbol": "SPY",
    "model_id": "lstm_test_v1",
    "lookback": 60,
}


def tick(price: float) -> dict:
    return {"price": price, "timestamp": 1_700_000_000_000}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# model_id / config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_model_id_stored_from_config(self):
        s = LSTMStrategy(BASE_CONFIG)
        assert s.model_id == "lstm_test_v1"

    def test_lookback_stored_from_config(self):
        s = LSTMStrategy({**BASE_CONFIG, "lookback": 30})
        assert s.lookback == 30


# ---------------------------------------------------------------------------
# Warmup guard
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_returns_none_before_warmup_period(self):
        s = LSTMStrategy(BASE_CONFIG)
        # Feed warmup_period - 1 ticks
        results = [run(s.on_tick(tick(100.0))) for _ in range(s.warmup_period - 1)]
        assert all(r is None for r in results)


# ---------------------------------------------------------------------------
# Feature validation (audit fix: no more silent `pass`)
# ---------------------------------------------------------------------------

class TestFeatureValidation:
    def test_missing_features_returns_none_and_logs_error(self, caplog):
        """If FeatureEngineer omits required columns, on_tick must return None
        with an error log, not raise an IndexError or KeyError."""
        import pandas as pd
        s = LSTMStrategy(BASE_CONFIG)
        s.warmup_period = 10
        s.lookback = 5

        # Build a minimal DataFrame missing most required features
        stub_df = pd.DataFrame({
            "open":  [100.0] * 20,
            "close": [100.0] * 20,
            # deliberately omitting RSI, MACD, ATR, BBU, BBL, BBM, etc.
        })

        with mock.patch.object(s.fe, "calculate_features", return_value=stub_df):
            # Pre-fill price buffer to skip warmup guard
            for _ in range(s.warmup_period):
                s.prices.append(100.0)

            with caplog.at_level(logging.ERROR, logger="TitanLSTM"):
                result = run(s.on_tick(tick(100.0)))

        assert result is None
        assert any("missing" in r.message.lower() or "feature" in r.message.lower()
                   for r in caplog.records), \
            "Expected an error log about missing feature columns"


# ---------------------------------------------------------------------------
# Inference error handling (audit fix)
# ---------------------------------------------------------------------------

class TestInferenceErrorHandling:
    def test_runtime_error_returns_none_and_logs(self, caplog):
        """RuntimeError from the model must be caught; on_tick returns None."""
        import pandas as pd
        s = LSTMStrategy(BASE_CONFIG)
        s.warmup_period = 10
        s.lookback = 5

        # Build a DataFrame with all required features
        stub_data = {col: [1.0] * 20 for col in _REQUIRED_FEATURES}
        stub_df = pd.DataFrame(stub_data)

        with mock.patch.object(s.fe, "calculate_features", return_value=stub_df):
            with mock.patch.object(s.model, "forward", side_effect=RuntimeError("mock OOM")):
                for _ in range(s.warmup_period):
                    s.prices.append(100.0)

                with caplog.at_level(logging.ERROR, logger="TitanLSTM"):
                    result = run(s.on_tick(tick(100.0)))

        assert result is None
        assert any("inference" in r.message.lower() or "failed" in r.message.lower()
                   for r in caplog.records), \
            "Expected an error log about inference failure"


# ---------------------------------------------------------------------------
# _REQUIRED_FEATURES constant
# ---------------------------------------------------------------------------

class TestRequiredFeatures:
    def test_required_features_has_14_entries(self):
        assert len(_REQUIRED_FEATURES) == 14, \
            f"LSTMModel input_size=14 but _REQUIRED_FEATURES has {len(_REQUIRED_FEATURES)}"

    def test_required_features_are_unique(self):
        assert len(_REQUIRED_FEATURES) == len(set(_REQUIRED_FEATURES)), \
            "Duplicate feature names in _REQUIRED_FEATURES"

    def test_on_bar_returns_none(self):
        s = LSTMStrategy(BASE_CONFIG)
        result = run(s.on_bar({}))
        assert result is None
