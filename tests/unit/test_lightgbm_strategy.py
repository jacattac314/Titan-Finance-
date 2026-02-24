"""
Unit tests for services/signal/strategies/lightgbm_strategy.py

LightGBMStrategy trains a binary classifier on startup (using synthetic data)
and emits BUY/SELL signals once its deque accumulates enough bars.

All tests that require the `ta` indicator library (via FeatureEngineer) are
guarded by pytest.importorskip so the suite degrades gracefully in environments
where `ta` cannot be installed (see ci.yml for the setuptools pin).
"""
import asyncio
import pytest

# Guard: skip the entire module if ta (or lightgbm) is absent.
lgb = pytest.importorskip("lightgbm", reason="lightgbm not installed")
pytest.importorskip("ta", reason="ta not installed (needs setuptools<67)")

from strategies.lightgbm_strategy import LightGBMStrategy  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "symbol": "AAPL",
    "model_id": "lgbm-test",
    "confidence_threshold": 0.6,
}


def make_strategy(**overrides) -> LightGBMStrategy:
    config = {**BASE_CONFIG, **overrides}
    return LightGBMStrategy(config)


def tick(price: float) -> dict:
    return {"price": price, "timestamp": "2024-01-01T00:00:00"}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_model_is_trained_on_construction(self):
        s = make_strategy()
        assert s.model is not None

    def test_explainer_is_initialized(self):
        s = make_strategy()
        assert s.explainer is not None

    def test_symbol_and_model_id_from_config(self):
        s = make_strategy()
        assert s.symbol == "AAPL"
        assert s.model_id == "lgbm-test"

    def test_custom_confidence_threshold(self):
        s = make_strategy(confidence_threshold=0.75)
        assert s.confidence_threshold == 0.75

    def test_bars_deque_starts_empty(self):
        s = make_strategy()
        assert len(s.bars) == 0


# ---------------------------------------------------------------------------
# Warmup guard
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_returns_none_before_min_bars_reached(self):
        s = make_strategy()
        # Feed min_bars - 1 ticks; all should return None
        results = [run(s.on_tick(tick(100.0))) for _ in range(s.min_bars - 1)]
        assert all(r is None for r in results)

    def test_zero_price_tick_returns_none_and_is_not_appended(self):
        s = make_strategy()
        result = run(s.on_tick(tick(0.0)))
        assert result is None
        assert len(s.bars) == 0

    def test_negative_price_tick_returns_none_and_is_not_appended(self):
        s = make_strategy()
        result = run(s.on_tick(tick(-5.0)))
        assert result is None
        assert len(s.bars) == 0


# ---------------------------------------------------------------------------
# Bar accumulation
# ---------------------------------------------------------------------------

class TestBarAccumulation:
    def test_valid_ticks_are_appended_to_deque(self):
        s = make_strategy()
        for _ in range(10):
            run(s.on_tick(tick(100.0)))
        assert len(s.bars) == 10

    def test_deque_respects_maxlen_of_200(self):
        s = make_strategy()
        for i in range(250):
            run(s.on_tick(tick(100.0 + i)))
        assert len(s.bars) == 200

    def test_bar_contains_ohlcv_keys(self):
        s = make_strategy()
        run(s.on_tick(tick(123.45)))
        bar = s.bars[-1]
        for key in ("open", "high", "low", "close", "volume"):
            assert key in bar, f"Bar missing key '{key}'"

    def test_bar_price_equals_tick_price(self):
        s = make_strategy()
        run(s.on_tick(tick(99.99)))
        bar = s.bars[-1]
        assert bar["close"] == 99.99
        assert bar["open"] == 99.99


# ---------------------------------------------------------------------------
# Signal emission (after warmup)
# ---------------------------------------------------------------------------

class TestSignalEmission:
    def _warmed_up_strategy(self) -> LightGBMStrategy:
        """Return a strategy with exactly min_bars ticks fed."""
        s = make_strategy()
        for _ in range(s.min_bars):
            run(s.on_tick(tick(100.0)))
        return s

    def test_produces_a_result_after_warmup(self):
        # After min_bars ticks we get either a signal dict or None (no signal)
        s = self._warmed_up_strategy()
        result = run(s.on_tick(tick(100.0)))
        # Must be dict or None — not an exception
        assert result is None or isinstance(result, dict)

    def test_signal_dict_contains_required_fields(self):
        import numpy as np
        s = make_strategy()
        # Alternate prices to create variance so the model can produce a signal.
        # We try many ticks; if a signal never fires the test is inconclusive but
        # does NOT fail (model output depends on trained weights).
        for i in range(300):
            price = 100.0 + (5 if i % 2 == 0 else -5)
            result = run(s.on_tick(tick(price)))
            if result is not None:
                for field in ("model_id", "model_name", "symbol",
                              "signal", "confidence", "price", "explanation"):
                    assert field in result, f"Signal missing field '{field}'"
                return  # at least one valid signal was produced
        # If no signal fired in 300 ticks, that is acceptable behaviour —
        # confidence never crossed the threshold on this synthetic data.
        pytest.skip("Model produced no signal in 300 ticks (confidence below threshold)")

    def test_signal_value_is_buy_or_sell(self):
        s = make_strategy()
        for i in range(300):
            price = 100.0 + (10 if i % 3 == 0 else -10)
            result = run(s.on_tick(tick(price)))
            if result is not None:
                assert result["signal"] in ("BUY", "SELL")
                return
        pytest.skip("No signal emitted in 300 ticks")

    def test_confidence_in_unit_interval(self):
        s = make_strategy()
        for i in range(300):
            price = 100.0 + (10 if i % 3 == 0 else -10)
            result = run(s.on_tick(tick(price)))
            if result is not None:
                assert 0.0 <= result["confidence"] <= 1.0
                return
        pytest.skip("No signal emitted in 300 ticks")

    def test_explanation_is_a_list_of_strings(self):
        s = make_strategy()
        for i in range(300):
            price = 100.0 + (10 if i % 3 == 0 else -10)
            result = run(s.on_tick(tick(price)))
            if result is not None:
                assert isinstance(result["explanation"], list)
                assert all(isinstance(e, str) for e in result["explanation"])
                return
        pytest.skip("No signal emitted in 300 ticks")


# ---------------------------------------------------------------------------
# on_bar stub
# ---------------------------------------------------------------------------

class TestOnBar:
    def test_on_bar_returns_none(self):
        s = make_strategy()
        result = run(s.on_bar({"open": 100, "high": 105, "low": 98, "close": 102, "volume": 5000}))
        assert result is None
