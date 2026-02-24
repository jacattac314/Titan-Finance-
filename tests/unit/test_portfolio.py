"""
Unit tests for services/execution/core/portfolio.py

VirtualPortfolio manages per-strategy cash, positions, and trade history.
The most critical path is update_from_fill: wrong cash arithmetic or
average-price calculation silently corrupts all P&L reporting.
"""
import pytest
from core.portfolio import VirtualPortfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_portfolio(cash: float = 100_000.0) -> VirtualPortfolio:
    return VirtualPortfolio("test-portfolio", starting_cash=cash)


def buy_fill(symbol: str, qty: int, price: float, ts: str = "2024-01-01T00:00:00") -> dict:
    return {"symbol": symbol, "qty": qty, "price": price, "side": "buy", "timestamp": ts}


def sell_fill(symbol: str, qty: int, price: float, ts: str = "2024-01-01T00:00:00") -> dict:
    return {"symbol": symbol, "qty": qty, "price": price, "side": "sell", "timestamp": ts}


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_starting_cash_is_set(self):
        vp = make_portfolio(50_000)
        assert vp.cash == 50_000
        assert vp.initial_cash == 50_000

    def test_no_positions_at_start(self):
        vp = make_portfolio()
        assert vp.positions == {}

    def test_history_and_equity_curve_empty_at_start(self):
        vp = make_portfolio()
        assert vp.history == []
        assert vp.equity_curve == []


# ---------------------------------------------------------------------------
# can_afford
# ---------------------------------------------------------------------------

class TestCanAfford:
    def test_returns_true_when_cash_is_sufficient(self):
        vp = make_portfolio(10_000)
        assert vp.can_afford("AAPL", 10, 100.0) is True  # cost = 1000

    def test_returns_false_when_cash_is_insufficient(self):
        vp = make_portfolio(500)
        assert vp.can_afford("AAPL", 10, 100.0) is False  # cost = 1000

    def test_sell_always_returns_true(self):
        # Selling reduces position, always adds cash
        vp = make_portfolio(0)
        assert vp.can_afford("AAPL", -10, 100.0) is True


# ---------------------------------------------------------------------------
# update_from_fill — buying
# ---------------------------------------------------------------------------

class TestUpdateFromFillBuy:
    def test_creates_new_position_on_first_buy(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        assert "AAPL" in vp.positions
        assert vp.positions["AAPL"]["qty"] == 10
        assert vp.positions["AAPL"]["avg_price"] == 100.0

    def test_cash_decreases_by_cost(self):
        vp = make_portfolio(10_000)
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        assert vp.cash == 9_000

    def test_average_price_weighted_correctly_on_second_buy(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))  # 10 shares @ 100
        vp.update_from_fill(buy_fill("AAPL", 10, 120.0))  # 10 shares @ 120
        # Weighted avg = (10*100 + 10*120) / 20 = 110
        assert vp.positions["AAPL"]["qty"] == 20
        assert vp.positions["AAPL"]["avg_price"] == 110.0

    def test_average_price_unequal_quantities(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 20, 100.0))  # cost = 2000
        vp.update_from_fill(buy_fill("AAPL", 10, 130.0))  # cost = 1300
        # Weighted avg = (20*100 + 10*130) / 30 = (2000+1300)/30 = 110
        assert vp.positions["AAPL"]["qty"] == 30
        assert abs(vp.positions["AAPL"]["avg_price"] - 110.0) < 1e-6

    def test_trade_appended_to_history(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        assert len(vp.history) == 1
        record = vp.history[0]
        assert record["symbol"] == "AAPL"
        assert record["side"] == "buy"
        assert record["qty"] == 10
        assert record["price"] == 100.0


# ---------------------------------------------------------------------------
# update_from_fill — selling
# ---------------------------------------------------------------------------

class TestUpdateFromFillSell:
    def test_sell_reduces_position_qty(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 20, 100.0))
        vp.update_from_fill(sell_fill("AAPL", 10, 110.0))
        assert vp.positions["AAPL"]["qty"] == 10

    def test_sell_increases_cash(self):
        vp = make_portfolio(10_000)
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))  # cash -> 9000
        vp.update_from_fill(sell_fill("AAPL", 10, 110.0))  # cash -> 9000 + 1100 = 10100
        assert vp.cash == 10_100

    def test_sell_to_zero_removes_position(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        vp.update_from_fill(sell_fill("AAPL", 10, 110.0))
        assert "AAPL" not in vp.positions

    def test_sell_avg_price_unchanged(self):
        # avg_price is only updated on buys
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 20, 100.0))
        vp.update_from_fill(sell_fill("AAPL", 10, 150.0))
        assert vp.positions["AAPL"]["avg_price"] == 100.0


# ---------------------------------------------------------------------------
# Multiple symbols
# ---------------------------------------------------------------------------

class TestMultipleSymbols:
    def test_positions_tracked_independently(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        vp.update_from_fill(buy_fill("MSFT", 5, 200.0))
        assert vp.positions["AAPL"]["qty"] == 10
        assert vp.positions["MSFT"]["qty"] == 5

    def test_cash_reflects_all_trades(self):
        vp = make_portfolio(10_000)
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))  # -1000
        vp.update_from_fill(buy_fill("MSFT", 5, 200.0))   # -1000
        assert vp.cash == 8_000


# ---------------------------------------------------------------------------
# get_market_value
# ---------------------------------------------------------------------------

class TestGetMarketValue:
    def test_zero_when_no_positions(self):
        vp = make_portfolio()
        assert vp.get_market_value({}) == 0.0

    def test_uses_provided_prices(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        value = vp.get_market_value({"AAPL": 150.0})
        assert value == 1_500.0

    def test_falls_back_to_avg_price_when_price_missing(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        value = vp.get_market_value({})  # no price provided
        assert value == 1_000.0  # 10 * avg_price(100)

    def test_sums_across_multiple_positions(self):
        vp = make_portfolio()
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        vp.update_from_fill(buy_fill("MSFT", 5, 200.0))
        value = vp.get_market_value({"AAPL": 110.0, "MSFT": 210.0})
        assert value == 10 * 110 + 5 * 210  # 1100 + 1050 = 2150


# ---------------------------------------------------------------------------
# calculate_total_equity
# ---------------------------------------------------------------------------

class TestCalculateTotalEquity:
    def test_equals_cash_with_no_positions(self):
        vp = make_portfolio(50_000)
        assert vp.calculate_total_equity({}) == 50_000

    def test_includes_position_market_value(self):
        vp = make_portfolio(10_000)
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))  # cash -> 9000
        equity = vp.calculate_total_equity({"AAPL": 120.0})
        assert equity == 9_000 + 1_200  # cash + 10*120


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_snapshot_appends_to_equity_curve(self):
        vp = make_portfolio(50_000)
        vp.snapshot({})
        assert len(vp.equity_curve) == 1
        assert vp.equity_curve[0]["equity"] == 50_000
        assert vp.equity_curve[0]["cash"] == 50_000

    def test_multiple_snapshots_build_curve(self):
        vp = make_portfolio(100_000)
        vp.snapshot({})
        vp.update_from_fill(buy_fill("AAPL", 10, 100.0))
        vp.snapshot({"AAPL": 110.0})
        assert len(vp.equity_curve) == 2
