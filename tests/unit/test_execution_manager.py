"""
Unit tests for services/execution/core/manager.py

PortfolioManager is the fill-routing hub for all strategies.
A misrouted fill silently corrupts the wrong portfolio's P&L, so every
routing path (order_id, strategy_id, model_id, orphan) is covered.
"""
import pytest
from core.manager import PortfolioManager
from core.portfolio import VirtualPortfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_manager() -> PortfolioManager:
    return PortfolioManager()


def buy_fill(**overrides) -> dict:
    base = {
        "order_id": "ord-1",
        "symbol": "AAPL",
        "qty": 10,
        "price": 100.0,
        "side": "buy",
        "timestamp": "2024-01-01T00:00:00",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# create_portfolio
# ---------------------------------------------------------------------------

class TestCreatePortfolio:
    def test_creates_portfolio_with_correct_cash(self):
        m = make_manager()
        vp = m.create_portfolio("strat-1", starting_cash=50_000)
        assert isinstance(vp, VirtualPortfolio)
        assert vp.cash == 50_000

    def test_portfolio_is_retrievable_after_creation(self):
        m = make_manager()
        m.create_portfolio("strat-1", starting_cash=50_000)
        assert m.get_portfolio("strat-1") is not None

    def test_creates_multiple_independent_portfolios(self):
        m = make_manager()
        m.create_portfolio("strat-A", starting_cash=100_000)
        m.create_portfolio("strat-B", starting_cash=200_000)
        assert m.get_portfolio("strat-A").cash == 100_000
        assert m.get_portfolio("strat-B").cash == 200_000

    def test_returns_existing_portfolio_when_id_already_registered(self):
        m = make_manager()
        vp1 = m.create_portfolio("strat-1", starting_cash=100_000)
        vp2 = m.create_portfolio("strat-1", starting_cash=99_999)  # duplicate call
        # Must return the original instance unchanged
        assert vp1 is vp2
        assert vp2.cash == 100_000

    def test_uses_default_starting_cash_of_100k(self):
        m = make_manager()
        vp = m.create_portfolio("strat-1")
        assert vp.cash == 100_000


# ---------------------------------------------------------------------------
# get_portfolio
# ---------------------------------------------------------------------------

class TestGetPortfolio:
    def test_returns_none_for_unknown_id(self):
        m = make_manager()
        assert m.get_portfolio("nonexistent") is None

    def test_returns_correct_instance_by_id(self):
        m = make_manager()
        m.create_portfolio("A")
        m.create_portfolio("B")
        vp_a = m.get_portfolio("A")
        vp_b = m.get_portfolio("B")
        assert vp_a is not vp_b


# ---------------------------------------------------------------------------
# register_order
# ---------------------------------------------------------------------------

class TestRegisterOrder:
    def test_order_id_mapped_to_portfolio(self):
        m = make_manager()
        m.register_order("ord-123", "strat-1")
        assert m.order_map["ord-123"] == "strat-1"

    def test_multiple_orders_map_to_same_portfolio(self):
        m = make_manager()
        m.register_order("ord-1", "strat-1")
        m.register_order("ord-2", "strat-1")
        assert m.order_map["ord-1"] == "strat-1"
        assert m.order_map["ord-2"] == "strat-1"

    def test_order_id_can_be_re_mapped(self):
        m = make_manager()
        m.register_order("ord-1", "strat-A")
        m.register_order("ord-1", "strat-B")
        assert m.order_map["ord-1"] == "strat-B"


# ---------------------------------------------------------------------------
# on_execution_fill — routing via order_id
# ---------------------------------------------------------------------------

class TestFillRoutingByOrderId:
    def test_fill_routes_to_correct_portfolio_via_order_id(self):
        m = make_manager()
        m.create_portfolio("strat-1", starting_cash=10_000)
        m.register_order("ord-1", "strat-1")
        m.on_execution_fill(buy_fill(order_id="ord-1", qty=10, price=100.0))
        vp = m.get_portfolio("strat-1")
        assert vp.cash == 9_000  # 10_000 - 10*100

    def test_fill_updates_position_in_correct_portfolio(self):
        m = make_manager()
        m.create_portfolio("strat-1")
        m.register_order("ord-1", "strat-1")
        m.on_execution_fill(buy_fill(order_id="ord-1", symbol="AAPL", qty=5, price=200.0))
        assert m.get_portfolio("strat-1").positions["AAPL"]["qty"] == 5

    def test_fill_does_not_affect_other_portfolios(self):
        m = make_manager()
        m.create_portfolio("strat-1", starting_cash=10_000)
        m.create_portfolio("strat-2", starting_cash=10_000)
        m.register_order("ord-1", "strat-1")
        m.on_execution_fill(buy_fill(order_id="ord-1", qty=10, price=100.0))
        # strat-2 must be untouched
        assert m.get_portfolio("strat-2").cash == 10_000
        assert m.get_portfolio("strat-2").positions == {}


# ---------------------------------------------------------------------------
# on_execution_fill — fallback routing via strategy_id / model_id
# ---------------------------------------------------------------------------

class TestFillRoutingFallback:
    def test_routes_via_strategy_id_when_order_id_not_registered(self):
        m = make_manager()
        m.create_portfolio("strat-ml", starting_cash=10_000)
        fill = buy_fill(order_id=None, qty=5, price=100.0)
        fill["strategy_id"] = "strat-ml"
        m.on_execution_fill(fill)
        assert m.get_portfolio("strat-ml").cash == 9_500  # 10_000 - 5*100

    def test_routes_via_model_id_when_strategy_id_absent(self):
        m = make_manager()
        m.create_portfolio("lgbm-v1", starting_cash=10_000)
        fill = buy_fill(order_id=None, qty=5, price=100.0)
        fill["model_id"] = "lgbm-v1"
        m.on_execution_fill(fill)
        assert m.get_portfolio("lgbm-v1").cash == 9_500

    def test_strategy_id_takes_priority_over_model_id(self):
        m = make_manager()
        m.create_portfolio("strat-A", starting_cash=10_000)
        m.create_portfolio("model-B", starting_cash=10_000)
        fill = buy_fill(order_id=None, qty=5, price=100.0)
        fill["strategy_id"] = "strat-A"
        fill["model_id"] = "model-B"
        m.on_execution_fill(fill)
        # strat-A receives the fill
        assert m.get_portfolio("strat-A").cash == 9_500
        # model-B is untouched
        assert m.get_portfolio("model-B").cash == 10_000


# ---------------------------------------------------------------------------
# on_execution_fill — orphan fill (no portfolio found)
# ---------------------------------------------------------------------------

class TestOrphanFill:
    def test_orphan_fill_does_not_raise(self):
        m = make_manager()
        # No portfolio registered at all
        try:
            m.on_execution_fill(buy_fill(order_id="unknown-ord"))
        except Exception as exc:
            pytest.fail(f"Orphan fill raised unexpected exception: {exc}")

    def test_orphan_fill_leaves_all_portfolios_unchanged(self):
        m = make_manager()
        m.create_portfolio("strat-1", starting_cash=10_000)
        m.on_execution_fill(buy_fill(order_id="unknown-ord", qty=10, price=100.0))
        assert m.get_portfolio("strat-1").cash == 10_000

    def test_orphan_fill_with_no_portfolios_at_all_does_not_raise(self):
        m = make_manager()
        try:
            m.on_execution_fill({"order_id": "x", "qty": 1, "price": 100.0, "side": "buy"})
        except Exception as exc:
            pytest.fail(f"Raised: {exc}")


# ---------------------------------------------------------------------------
# get_all_portfolios
# ---------------------------------------------------------------------------

class TestGetAllPortfolios:
    def test_returns_empty_list_when_no_portfolios(self):
        m = make_manager()
        assert m.get_all_portfolios() == []

    def test_returns_one_entry_per_portfolio(self):
        m = make_manager()
        m.create_portfolio("A")
        m.create_portfolio("B")
        result = m.get_all_portfolios()
        assert len(result) == 2

    def test_summary_contains_required_keys(self):
        m = make_manager()
        m.create_portfolio("strat-1", starting_cash=50_000)
        summary = m.get_all_portfolios()[0]
        for key in ("id", "cash", "positions_count", "equity"):
            assert key in summary, f"Missing key '{key}' in portfolio summary"

    def test_summary_values_reflect_portfolio_state(self):
        m = make_manager()
        m.create_portfolio("strat-1", starting_cash=50_000)
        m.register_order("ord-1", "strat-1")
        m.on_execution_fill(buy_fill(order_id="ord-1", symbol="AAPL", qty=10, price=100.0))
        summary = m.get_all_portfolios()[0]
        assert summary["id"] == "strat-1"
        assert summary["cash"] == 49_000
        assert summary["positions_count"] == 1
