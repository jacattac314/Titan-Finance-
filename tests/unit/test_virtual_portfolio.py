"""
Unit tests for services/execution/virtual_portfolio.py

VirtualPortfolio tracks per-model cash, positions, and realized P&L.
VirtualPortfolioManager routes signals to isolated portfolios and enforces
risk-sizing / model-cap limits.
"""
import pytest
from virtual_portfolio import VirtualPortfolio, VirtualPortfolioManager, TradeFill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_portfolio(starting_cash: float = 10_000.0) -> VirtualPortfolio:
    return VirtualPortfolio("m1", "Model One", starting_cash=starting_cash)


def make_manager(**overrides) -> VirtualPortfolioManager:
    defaults = dict(starting_cash=10_000, risk_per_trade=0.10, min_confidence=0.25)
    defaults.update(overrides)
    return VirtualPortfolioManager(**defaults)


def buy_signal(**overrides) -> dict:
    base = {
        "signal": "BUY",
        "symbol": "AAPL",
        "model_id": "m1",
        "model_name": "M1",
        "confidence": 0.8,
        "price": 100.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# VirtualPortfolio.buy
# ---------------------------------------------------------------------------

class TestBuy:
    def test_buy_creates_position(self):
        vp = make_portfolio()
        fill = vp.buy("AAPL", price=100.0, budget=1_000.0)
        assert fill is not None
        assert "AAPL" in vp.positions
        assert vp.positions["AAPL"].qty == 10

    def test_buy_reduces_cash(self):
        vp = make_portfolio(10_000)
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        assert vp.cash == 9_000

    def test_buy_budget_capped_by_available_cash(self):
        vp = make_portfolio(500)
        fill = vp.buy("AAPL", price=100.0, budget=10_000.0)  # wants 10k, only has 500
        assert fill is not None
        assert fill.qty == 5
        assert vp.cash == 0

    def test_buy_returns_none_for_zero_price(self):
        vp = make_portfolio()
        assert vp.buy("AAPL", price=0.0, budget=1_000.0) is None

    def test_buy_returns_none_for_zero_budget(self):
        vp = make_portfolio()
        assert vp.buy("AAPL", price=100.0, budget=0.0) is None

    def test_buy_updates_avg_cost_weighted(self):
        vp = make_portfolio(10_000)
        vp.buy("AAPL", price=100.0, budget=1_000.0)  # 10 @ 100
        vp.buy("AAPL", price=200.0, budget=2_000.0)  # 10 @ 200
        # weighted avg = (10*100 + 10*200) / 20 = 150
        assert vp.positions["AAPL"].avg_cost == pytest.approx(150.0)

    def test_buy_increments_trade_counter(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        assert vp.trades == 1

    def test_buy_returns_trade_fill_with_correct_side(self):
        vp = make_portfolio()
        fill = vp.buy("AAPL", price=100.0, budget=1_000.0)
        assert isinstance(fill, TradeFill)
        assert fill.side == "BUY"
        assert fill.symbol == "AAPL"


# ---------------------------------------------------------------------------
# VirtualPortfolio.sell
# ---------------------------------------------------------------------------

class TestSell:
    def test_sell_reduces_position_qty(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=2_000.0)  # 20 shares
        vp.sell("AAPL", price=110.0, qty=10)
        assert vp.positions["AAPL"].qty == 10

    def test_sell_increases_cash(self):
        vp = make_portfolio(10_000)
        vp.buy("AAPL", price=100.0, budget=1_000.0)  # cash → 9000, 10 shares
        vp.sell("AAPL", price=110.0)                  # sell all → +1100
        assert vp.cash == pytest.approx(10_100.0)

    def test_sell_computes_correct_realized_pnl(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)  # 10 @ 100
        fill = vp.sell("AAPL", price=150.0)
        assert fill.realized_pnl == pytest.approx(500.0)  # 10 * (150-100)

    def test_full_sell_zeroes_position_qty(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        vp.sell("AAPL", price=100.0)
        assert vp.positions["AAPL"].qty == 0

    def test_sell_returns_none_when_no_position(self):
        vp = make_portfolio()
        assert vp.sell("AAPL", price=100.0) is None

    def test_sell_returns_none_for_zero_price(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        assert vp.sell("AAPL", price=0.0) is None

    def test_profitable_sell_increments_wins(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        vp.sell("AAPL", price=110.0)
        assert vp.wins == 1

    def test_losing_sell_does_not_increment_wins(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        vp.sell("AAPL", price=90.0)
        assert vp.wins == 0

    def test_sell_increments_closed_trades(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        vp.sell("AAPL", price=100.0)
        assert vp.closed_trades == 1


# ---------------------------------------------------------------------------
# VirtualPortfolio.mark_to_market
# ---------------------------------------------------------------------------

class TestMarkToMarket:
    def test_no_positions_returns_cash(self):
        vp = make_portfolio(50_000)
        assert vp.mark_to_market({}) == pytest.approx(50_000)

    def test_includes_position_at_live_price(self):
        vp = make_portfolio(10_000)
        vp.buy("AAPL", price=100.0, budget=1_000.0)  # 10 shares, cash → 9000
        mtm = vp.mark_to_market({"AAPL": 120.0})
        assert mtm == pytest.approx(9_000 + 10 * 120)

    def test_falls_back_to_avg_cost_when_price_missing(self):
        vp = make_portfolio(10_000)
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        mtm = vp.mark_to_market({})
        assert mtm == pytest.approx(9_000 + 10 * 100)


# ---------------------------------------------------------------------------
# VirtualPortfolio.snapshot
# ---------------------------------------------------------------------------

class TestSnapshot:
    REQUIRED_KEYS = ("model_id", "cash", "equity", "pnl", "pnl_pct",
                     "realized_pnl", "trades", "wins", "closed_trades",
                     "win_rate", "open_positions")

    def test_snapshot_returns_required_keys(self):
        vp = make_portfolio()
        snap = vp.snapshot({})
        for key in self.REQUIRED_KEYS:
            assert key in snap, f"Missing key '{key}'"

    def test_snapshot_pnl_reflects_realized_gain(self):
        vp = make_portfolio(10_000)
        vp.buy("AAPL", price=100.0, budget=1_000.0)   # 10 @ 100
        vp.sell("AAPL", price=200.0)                    # 10 @ 200 → +1000
        snap = vp.snapshot({})
        assert snap["pnl"] == pytest.approx(1_000.0)

    def test_win_rate_zero_when_no_closed_trades(self):
        vp = make_portfolio()
        assert vp.snapshot({})["win_rate"] == 0.0

    def test_open_positions_count(self):
        vp = make_portfolio()
        vp.buy("AAPL", price=100.0, budget=1_000.0)
        vp.buy("MSFT", price=200.0, budget=2_000.0)
        assert vp.snapshot({})["open_positions"] == 2


# ---------------------------------------------------------------------------
# VirtualPortfolioManager
# ---------------------------------------------------------------------------

class TestVirtualPortfolioManager:
    def test_buy_signal_creates_portfolio_and_returns_fill(self):
        mgr = make_manager()
        mgr.update_price("AAPL", 100.0)
        result = mgr.apply_signal(buy_signal())
        assert result is not None
        portfolio, fill = result
        assert fill.side == "BUY"
        assert fill.symbol == "AAPL"

    def test_sell_without_position_returns_none(self):
        mgr = make_manager()
        mgr.update_price("AAPL", 100.0)
        result = mgr.apply_signal({"signal": "SELL", "symbol": "AAPL",
                                    "model_id": "m1", "model_name": "M1", "confidence": 0.5})
        assert result is None

    def test_buy_then_sell_reduces_position(self):
        mgr = make_manager()
        mgr.update_price("AAPL", 100.0)
        mgr.apply_signal(buy_signal())
        result = mgr.apply_signal({"signal": "SELL", "symbol": "AAPL",
                                    "model_id": "m1", "model_name": "M1", "confidence": 0.5})
        assert result is not None

    def test_max_models_cap_is_enforced(self):
        mgr = make_manager(max_models=1)
        mgr.update_price("AAPL", 100.0)
        mgr.apply_signal(buy_signal(model_id="m1"))
        result = mgr.apply_signal(buy_signal(model_id="m2"))  # would be second model
        assert result is None

    def test_unknown_signal_returns_none(self):
        mgr = make_manager()
        result = mgr.apply_signal({"signal": "HOLD", "symbol": "AAPL",
                                    "model_id": "m1", "model_name": "M1"})
        assert result is None

    def test_missing_symbol_returns_none(self):
        mgr = make_manager()
        result = mgr.apply_signal({"signal": "BUY", "model_id": "m1",
                                    "model_name": "M1", "confidence": 0.8})
        assert result is None

    def test_zero_price_returns_none(self):
        mgr = make_manager()
        # No price in last_prices and signal price is absent
        result = mgr.apply_signal(buy_signal(price=None))
        assert result is None

    def test_update_price_stores_latest(self):
        mgr = make_manager()
        mgr.update_price("SPY", 450.0)
        assert mgr.last_prices["SPY"] == 450.0

    def test_update_price_ignores_nonpositive(self):
        mgr = make_manager()
        mgr.update_price("SPY", 0.0)
        assert "SPY" not in mgr.last_prices

    def test_leaderboard_sorted_by_pnl_descending(self):
        mgr = make_manager()
        mgr.update_price("AAPL", 100.0)
        mgr.update_price("MSFT", 200.0)
        mgr.apply_signal(buy_signal(model_id="m1", symbol="AAPL"))
        mgr.apply_signal(buy_signal(model_id="m2", symbol="MSFT", price=200.0))
        lb = mgr.leaderboard()
        assert len(lb) == 2
        assert lb[0]["pnl"] >= lb[1]["pnl"]

    def test_leaderboard_empty_when_no_portfolios(self):
        mgr = make_manager()
        assert mgr.leaderboard() == []

    def test_same_model_reuses_portfolio(self):
        mgr = make_manager()
        mgr.update_price("AAPL", 100.0)
        mgr.apply_signal(buy_signal(model_id="m1"))
        mgr.apply_signal(buy_signal(model_id="m1"))
        assert len(mgr.portfolios) == 1
