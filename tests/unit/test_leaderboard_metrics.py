"""
Unit tests for VirtualPortfolio leaderboard metrics.

Covers max_drawdown, sortino_ratio, calmar_ratio, and performance_summary.
These metrics directly drive the model-arena leaderboard ranking.
"""
import pytest
from core.portfolio import VirtualPortfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_portfolio(starting_cash: float = 100_000.0) -> VirtualPortfolio:
    return VirtualPortfolio("test_model", starting_cash)


def _push_equities(portfolio: VirtualPortfolio, values: list[float]):
    """Directly populate the equity curve without needing real prices."""
    for v in values:
        portfolio.equity_curve.append({"timestamp": "t", "equity": v, "cash": v})


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_returns_zero_with_fewer_than_two_points(self):
        p = make_portfolio()
        assert p.max_drawdown() == 0.0

    def test_returns_zero_when_equity_only_rises(self):
        p = make_portfolio()
        _push_equities(p, [100_000, 105_000, 110_000, 115_000])
        assert p.max_drawdown() == 0.0

    def test_correct_drawdown_after_single_drop(self):
        # Peak 110k → trough 99k → drawdown = 10%
        p = make_portfolio()
        _push_equities(p, [100_000, 110_000, 99_000])
        assert abs(p.max_drawdown() - 0.10) < 1e-3

    def test_max_drawdown_picks_worst_trough(self):
        # Two drops: 10% and 20% — should report 0.20
        p = make_portfolio()
        _push_equities(p, [100_000, 110_000, 99_000, 115_000, 92_000])
        assert p.max_drawdown() == pytest.approx(0.20, abs=1e-3)

    def test_returns_value_between_zero_and_one(self):
        p = make_portfolio()
        _push_equities(p, [100_000, 50_000, 30_000, 80_000])
        dd = p.max_drawdown()
        assert 0.0 <= dd <= 1.0


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------

class TestSortinoRatio:
    def test_returns_none_with_fewer_than_five_points(self):
        p = make_portfolio()
        _push_equities(p, [100_000, 101_000, 102_000, 101_000])
        assert p.sortino_ratio() is None

    def test_returns_none_when_no_negative_returns(self):
        # Purely rising curve has zero downside deviation → undefined
        p = make_portfolio()
        _push_equities(p, [100_000, 101_000, 102_000, 103_000, 104_000, 105_000])
        assert p.sortino_ratio() is None

    def test_positive_for_net_positive_returns_with_some_downside(self):
        # Overall upward trend with occasional dips → positive Sortino
        p = make_portfolio()
        _push_equities(p, [100_000, 102_000, 101_000, 103_000, 102_500, 104_000, 103_000, 105_000])
        ratio = p.sortino_ratio()
        assert ratio is not None
        assert ratio > 0

    def test_negative_for_net_negative_returns(self):
        p = make_portfolio()
        _push_equities(p, [100_000, 98_000, 96_000, 95_000, 93_000, 92_000])
        ratio = p.sortino_ratio()
        assert ratio is not None
        assert ratio < 0


# ---------------------------------------------------------------------------
# calmar_ratio
# ---------------------------------------------------------------------------

class TestCalmarRatio:
    def test_returns_none_with_fewer_than_two_points(self):
        p = make_portfolio()
        assert p.calmar_ratio() is None

    def test_returns_none_when_max_drawdown_is_zero(self):
        # No drawdown → Calmar is undefined (division by zero guard)
        p = make_portfolio()
        _push_equities(p, [100_000, 102_000, 104_000, 106_000])
        assert p.calmar_ratio() is None

    def test_positive_calmar_when_positive_return_with_drawdown(self):
        # Start 100k → dip to 95k → end at 110k: positive total return, 5% drawdown
        p = make_portfolio()
        _push_equities(p, [100_000, 95_000, 110_000])
        ratio = p.calmar_ratio()
        assert ratio is not None
        assert ratio > 0

    def test_calmar_ratio_value(self):
        # total_return = (110k - 100k) / 100k = 10%
        # max_drawdown = (100k - 95k) / 100k = 5% = 0.05
        # calmar = 0.10 / 0.05 = 2.0
        p = make_portfolio()
        _push_equities(p, [100_000, 95_000, 110_000])
        assert p.calmar_ratio() == pytest.approx(2.0, abs=0.01)

    def test_negative_calmar_when_net_loss(self):
        p = make_portfolio()
        _push_equities(p, [100_000, 90_000, 85_000])
        ratio = p.calmar_ratio()
        assert ratio is not None
        assert ratio < 0


# ---------------------------------------------------------------------------
# performance_summary
# ---------------------------------------------------------------------------

class TestPerformanceSummary:
    def test_summary_contains_required_keys(self):
        p = make_portfolio()
        _push_equities(p, [100_000, 102_000])
        summary = p.performance_summary({})

        required = {
            "id", "cash", "equity", "positions_count",
            "total_return_pct", "max_drawdown_pct",
            "sortino_ratio", "calmar_ratio", "snapshot_count",
        }
        assert required <= set(summary.keys())

    def test_summary_records_a_new_snapshot(self):
        p = make_portfolio()
        initial_count = len(p.equity_curve)
        p.performance_summary({})
        assert len(p.equity_curve) == initial_count + 1

    def test_total_return_pct_is_correct(self):
        p = make_portfolio(starting_cash=100_000.0)
        # Manually give it $10k profit via a fill
        p.cash = 110_000.0
        summary = p.performance_summary({})
        assert summary["total_return_pct"] == pytest.approx(10.0, abs=0.01)

    def test_max_drawdown_pct_is_percentage(self):
        p = make_portfolio()
        _push_equities(p, [100_000, 80_000])  # 20% drawdown
        summary = p.performance_summary({})
        # max_drawdown_pct should be 20.0 (percent), not 0.20 (fraction)
        assert summary["max_drawdown_pct"] == pytest.approx(20.0, abs=0.1)
