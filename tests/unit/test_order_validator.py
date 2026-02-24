"""
Unit tests for services/execution/risk/validator.py

OrderValidator is the final pre-trade gate: it must correctly reject
invalid orders while accepting every legitimate one.  A false-negative
(accepting a bad order) has direct financial consequences.
"""
import pytest
from core.portfolio import VirtualPortfolio
from risk.validator import OrderValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_validator() -> OrderValidator:
    return OrderValidator()


def make_portfolio(cash: float = 100_000.0) -> VirtualPortfolio:
    vp = VirtualPortfolio("test", starting_cash=cash)
    return vp


# ---------------------------------------------------------------------------
# Basic input validation
# ---------------------------------------------------------------------------

class TestInvalidInputs:
    def test_rejects_zero_qty(self):
        v = make_validator()
        assert v.validate(make_portfolio(), "AAPL", 100.0, 0, "BUY") is False

    def test_rejects_negative_qty(self):
        v = make_validator()
        assert v.validate(make_portfolio(), "AAPL", 100.0, -5, "BUY") is False

    def test_rejects_zero_price(self):
        v = make_validator()
        assert v.validate(make_portfolio(), "AAPL", 0.0, 10, "BUY") is False

    def test_rejects_negative_price(self):
        v = make_validator()
        assert v.validate(make_portfolio(), "AAPL", -1.0, 10, "BUY") is False


# ---------------------------------------------------------------------------
# Buying power check (BUY only)
# ---------------------------------------------------------------------------

class TestBuyingPower:
    def test_rejects_buy_when_insufficient_cash(self):
        v = make_validator()
        vp = make_portfolio(cash=500)
        # 10 shares @ 100 = $1000 > $500 cash
        assert v.validate(vp, "AAPL", 100.0, 10, "BUY") is False

    def test_accepts_buy_when_cash_exactly_covers_cost(self):
        v = make_validator()
        vp = make_portfolio(cash=1_000)
        assert v.validate(vp, "AAPL", 100.0, 10, "BUY") is True

    def test_accepts_buy_when_cash_exceeds_cost(self):
        v = make_validator()
        vp = make_portfolio(cash=10_000)
        assert v.validate(vp, "AAPL", 100.0, 10, "BUY") is True

    def test_no_cash_check_for_sell(self):
        # Sells add cash; should not be blocked by insufficient cash
        v = make_validator()
        vp = make_portfolio(cash=0)
        assert v.validate(vp, "AAPL", 100.0, 10, "SELL") is True


# ---------------------------------------------------------------------------
# Max order value ($50,000)
# ---------------------------------------------------------------------------

class TestMaxOrderValue:
    def test_rejects_buy_exceeding_max_order_value(self):
        v = make_validator()
        vp = make_portfolio(cash=100_000)
        # 600 shares @ 100 = $60,000 > $50,000 limit
        assert v.validate(vp, "AAPL", 100.0, 600, "BUY") is False

    def test_buy_exactly_at_max_order_value_rejected_by_position_limit(self):
        # MAX_ORDER_VALUE=$50k but MAX_POS_SIZE=$25k: a fresh $50k order always
        # fails the position-size check before it can "pass" the order-value check.
        # This test documents that the effective single-order buy ceiling is $25k.
        v = make_validator()
        vp = make_portfolio(cash=100_000)
        # 500 shares @ $100 = $50,000 — hits MAX_POS_SIZE ($25k) first
        assert v.validate(vp, "AAPL", 100.0, 500, "BUY") is False

    def test_rejects_sell_exceeding_max_order_value(self):
        v = make_validator()
        vp = make_portfolio(cash=100_000)
        # SELL is also subject to MAX_ORDER_VALUE
        assert v.validate(vp, "AAPL", 100.0, 600, "SELL") is False


# ---------------------------------------------------------------------------
# Max position size ($25,000)
# ---------------------------------------------------------------------------

class TestMaxPositionSize:
    def test_rejects_buy_that_pushes_position_over_limit(self):
        v = make_validator()
        vp = make_portfolio(cash=100_000)
        # Existing position: 200 shares @ 100 = $20,000
        vp.positions["AAPL"] = {"qty": 200, "avg_price": 100.0}
        # New buy: 60 shares @ 100 = $6,000 → total $26,000 > $25,000
        assert v.validate(vp, "AAPL", 100.0, 60, "BUY") is False

    def test_accepts_buy_that_stays_within_position_limit(self):
        v = make_validator()
        vp = make_portfolio(cash=100_000)
        # Existing: 200 shares @ 100 = $20,000
        vp.positions["AAPL"] = {"qty": 200, "avg_price": 100.0}
        # New buy: 50 shares @ 100 = $5,000 → total $25,000 == limit
        assert v.validate(vp, "AAPL", 100.0, 50, "BUY") is True

    def test_new_position_within_limit_accepted(self):
        v = make_validator()
        vp = make_portfolio(cash=100_000)
        # 100 shares @ 100 = $10,000 < $25,000
        assert v.validate(vp, "AAPL", 100.0, 100, "BUY") is True


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_typical_valid_buy_order(self):
        v = make_validator()
        vp = make_portfolio(cash=50_000)
        # 50 shares @ 200 = $10,000 — within all limits
        assert v.validate(vp, "MSFT", 200.0, 50, "BUY") is True

    def test_typical_valid_sell_order(self):
        v = make_validator()
        vp = make_portfolio(cash=0)
        vp.positions["MSFT"] = {"qty": 50, "avg_price": 200.0}
        assert v.validate(vp, "MSFT", 210.0, 50, "SELL") is True
