"""
Unit tests for services/execution/simulation/slippage.py

SlippageModel applies directional slippage: BUY execution price must be
above the decision price, SELL must be below.  A sign inversion here
corrupts every simulated P&L figure.

Tests use random.seed() for determinism where the stochastic component
would otherwise make assertions unreliable.
"""
import random
import pytest
from simulation.slippage import SlippageModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_model(base_bps: int = 5) -> SlippageModel:
    return SlippageModel(base_bps=base_bps)


# ---------------------------------------------------------------------------
# Direction invariants
# ---------------------------------------------------------------------------

class TestSlippageDirection:
    def test_buy_price_is_above_decision_price(self):
        random.seed(42)
        model = make_model(base_bps=5)
        result = model.calculate_price(100.0, "BUY", 100)
        assert result > 100.0

    def test_sell_price_is_below_decision_price(self):
        random.seed(42)
        model = make_model(base_bps=5)
        result = model.calculate_price(100.0, "SELL", 100)
        assert result < 100.0

    def test_buy_direction_holds_across_many_seeds(self):
        model = make_model(base_bps=5)
        for seed in range(50):
            random.seed(seed)
            result = model.calculate_price(200.0, "BUY", 10)
            assert result > 200.0, f"BUY slippage went wrong direction at seed={seed}"

    def test_sell_direction_holds_across_many_seeds(self):
        model = make_model(base_bps=5)
        for seed in range(50):
            random.seed(seed)
            result = model.calculate_price(200.0, "SELL", 10)
            assert result < 200.0, f"SELL slippage went wrong direction at seed={seed}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestSlippageEdgeCases:
    def test_zero_decision_price_returned_unchanged(self):
        model = make_model()
        assert model.calculate_price(0.0, "BUY", 100) == 0.0

    def test_negative_decision_price_returned_unchanged(self):
        model = make_model()
        assert model.calculate_price(-50.0, "SELL", 10) == -50.0

    def test_result_is_rounded_to_two_decimal_places(self):
        random.seed(0)
        model = make_model()
        result = model.calculate_price(100.0, "BUY", 10)
        assert result == round(result, 2)


# ---------------------------------------------------------------------------
# Base bps effect
# ---------------------------------------------------------------------------

class TestBaseBps:
    def test_higher_base_bps_produces_larger_slippage_on_buy(self):
        # With the noise seeded identically, higher bps must produce a higher buy price
        low_model = make_model(base_bps=1)
        high_model = make_model(base_bps=50)

        random.seed(99)
        low_result = low_model.calculate_price(100.0, "BUY", 10)
        random.seed(99)
        high_result = high_model.calculate_price(100.0, "BUY", 10)

        assert high_result > low_result

    def test_higher_base_bps_produces_lower_sell_price(self):
        low_model = make_model(base_bps=1)
        high_model = make_model(base_bps=50)

        random.seed(99)
        low_result = low_model.calculate_price(100.0, "SELL", 10)
        random.seed(99)
        high_result = high_model.calculate_price(100.0, "SELL", 10)

        assert high_result < low_result


# ---------------------------------------------------------------------------
# Market impact (larger qty → more slippage)
# ---------------------------------------------------------------------------

class TestMarketImpact:
    def test_larger_qty_produces_higher_buy_price(self):
        # The impact formula is `(qty / 10_000) * 0.00005`, so the difference
        # only survives rounding to 2 dp when quantities differ by a large
        # enough factor.  Use qty=100 vs qty=1_000_000 for a clear $0.50 gap.
        model = make_model(base_bps=5)

        random.seed(7)
        small_result = model.calculate_price(100.0, "BUY", 100)
        random.seed(7)
        large_result = model.calculate_price(100.0, "BUY", 1_000_000)

        assert large_result > small_result
