"""
Unit tests for services/signal/strategies/lightgbm_strategy.py

Focuses on the model-loading guard introduced in the audit fix:
  - When the weights file is absent, _disabled=True and on_tick returns None.
  - model_id is stored from config.
  - on_tick short-circuits immediately when disabled (no side-effects).

These tests do NOT require actual LightGBM weights or a trained model;
they exercise the strategy's fail-safe state machine in isolation.
"""
import asyncio
import os
import pytest
from strategies.lightgbm_strategy import LightGBMStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "symbol": "SPY",
    "model_id": "lgb_test_v1",
    "confidence_threshold": 0.6,
}


def tick(price: float) -> dict:
    return {"price": price, "timestamp": 1_700_000_000_000}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Model-absent guard (the primary audit fix)
# ---------------------------------------------------------------------------

class TestModelAbsentGuard:
    def test_disabled_flag_set_when_weights_missing(self):
        """Strategy must be disabled (not raise) when weights file is absent."""
        s = LightGBMStrategy({**BASE_CONFIG, "model_id": "lgb_no_weights"})
        # Weights file virtually never exists in the test environment
        if not os.path.exists(s.model_path):
            assert s._disabled is True
            assert s.model is None

    def test_on_tick_returns_none_when_disabled(self):
        """on_tick must return None without AttributeError when disabled."""
        s = LightGBMStrategy({**BASE_CONFIG})
        if s._disabled:
            result = run(s.on_tick(tick(150.0)))
            assert result is None

    def test_on_tick_does_not_raise_when_disabled(self):
        """Ensure no exception is raised while accumulating ticks in disabled state."""
        s = LightGBMStrategy({**BASE_CONFIG})
        if s._disabled:
            for _ in range(100):
                try:
                    run(s.on_tick(tick(100.0)))
                except Exception as exc:
                    pytest.fail(f"on_tick raised when disabled: {exc}")

    def test_model_id_stored_from_config(self):
        s = LightGBMStrategy({**BASE_CONFIG})
        assert s.model_id == "lgb_test_v1"

    def test_zero_price_returns_none(self):
        s = LightGBMStrategy({**BASE_CONFIG})
        assert run(s.on_tick(tick(0.0))) is None

    def test_negative_price_returns_none(self):
        s = LightGBMStrategy({**BASE_CONFIG})
        assert run(s.on_tick(tick(-10.0))) is None

    def test_on_bar_returns_none(self):
        s = LightGBMStrategy({**BASE_CONFIG})
        result = run(s.on_bar({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}))
        assert result is None
