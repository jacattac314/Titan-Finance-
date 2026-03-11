"""
Integration tests for the RiskEngine kill-switch under realistic conditions.

These tests exercise the full lifecycle — account state update → kill-switch
evaluation → downstream effects on signal validation and position sizing —
ensuring that real drawdown or loss-streak scenarios halt trading correctly.
"""
import pytest
from risk_engine import RiskEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(**overrides):
    """Return a RiskEngine with a 100k account and 3% loss limit."""
    config = {
        "MAX_DAILY_LOSS_PCT": 0.03,
        "RISK_PER_TRADE_PCT": 0.01,
        "MAX_CONSECUTIVE_LOSSES": 5,
        "ROLLBACK_MIN_SHARPE": 0.50,
        "ROLLBACK_MIN_ACCURACY": 0.50,
    }
    config.update(overrides)
    return RiskEngine(config)


# ---------------------------------------------------------------------------
# Drawdown breach
# ---------------------------------------------------------------------------

class TestDrawdownBreach:
    def test_drawdown_breach_activates_kill_switch(self):
        """3% drawdown on a 100k account must fire the kill switch."""
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        # starting_equity = 97_000 - (-3_000) = 100_000
        engine.update_account_state(equity=97_000, daily_pnl=-3_000)
        result = engine.check_kill_switch()
        assert result is True
        assert engine.is_kill_switch_active is True

    def test_drawdown_breach_makes_validate_signal_return_false(self):
        """After a drawdown breach, validate_signal must reject every signal."""
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=97_000, daily_pnl=-3_000)
        engine.check_kill_switch()
        assert engine.validate_signal({}) is False
        assert engine.validate_signal({"symbol": "SPY", "signal": "BUY"}) is False

    def test_no_false_trigger_below_limit(self):
        """2.9% loss on a 3% limit must NOT trigger the kill switch."""
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        # starting_equity = 97_100 - (-2_900) = 100_000
        # drawdown_pct = -2_900 / 100_000 = -0.029 > -0.03 → no trigger
        engine.update_account_state(equity=97_100, daily_pnl=-2_900)
        result = engine.check_kill_switch()
        assert result is False
        assert engine.is_kill_switch_active is False


# ---------------------------------------------------------------------------
# Consecutive loss breach
# ---------------------------------------------------------------------------

class TestConsecutiveLossBreach:
    def test_five_consecutive_losses_fire_kill_switch(self):
        """Exactly 5 consecutive losses must activate the kill switch."""
        engine = make_engine(MAX_CONSECUTIVE_LOSSES=5)
        engine.update_account_state(equity=100_000, daily_pnl=0)
        for _ in range(5):
            engine.record_trade_result(-100)
        assert engine.check_kill_switch() is True
        assert engine.is_kill_switch_active is True


# ---------------------------------------------------------------------------
# Kill switch blocks position sizing
# ---------------------------------------------------------------------------

class TestKillSwitchBlocksPositionSizing:
    def test_position_size_is_zero_when_kill_switch_active(self):
        """calculate_position_size must return 0 whenever the kill switch is on."""
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=97_000, daily_pnl=-3_000)
        engine.check_kill_switch()
        assert engine.is_kill_switch_active is True
        assert engine.calculate_position_size(100.0, 95.0) == 0

    def test_position_size_is_nonzero_before_kill_switch(self):
        """Sanity check: position sizing works normally before kill-switch fires."""
        engine = make_engine(RISK_PER_TRADE_PCT=0.01)
        engine.update_account_state(equity=100_000, daily_pnl=0)
        # risk_amount = 1000, risk_per_share = 5 → floor(200)
        assert engine.calculate_position_size(100.0, 95.0) == 200


# ---------------------------------------------------------------------------
# reset_kill_switch
# ---------------------------------------------------------------------------

class TestResetKillSwitch:
    def test_reset_clears_flag_and_re_anchors_equity(self):
        """reset_kill_switch must clear the active flag and re-anchor starting_equity."""
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=97_000, daily_pnl=-3_000)
        engine.check_kill_switch()
        assert engine.is_kill_switch_active is True

        # Equity has partially recovered before the operator resets
        engine.current_equity = 98_500
        engine.reset_kill_switch()

        assert engine.is_kill_switch_active is False
        assert engine.starting_equity == 98_500
        assert engine.daily_pnl == 0.0
        assert engine.consecutive_losses == 0

    def test_validate_signal_resumes_after_reset(self):
        """After reset, signals must be accepted again (no manual-approval mode)."""
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=97_000, daily_pnl=-3_000)
        engine.check_kill_switch()
        engine.current_equity = 99_000
        engine.reset_kill_switch()
        assert engine.validate_signal({"symbol": "AAPL"}) is True


# ---------------------------------------------------------------------------
# Manual-approval mode blocks signals
# ---------------------------------------------------------------------------

class TestManualApprovalModeBlocking:
    def test_validate_signal_false_in_manual_approval_mode(self):
        """validate_signal must return False when manual-approval mode is on."""
        engine = make_engine()
        engine.is_manual_approval_mode = True
        assert engine.validate_signal({}) is False
        assert engine.validate_signal({"symbol": "TSLA", "signal": "SELL"}) is False


# ---------------------------------------------------------------------------
# Both conditions simultaneously
# ---------------------------------------------------------------------------

class TestBothConditionsSimultaneously:
    def test_drawdown_and_consecutive_losses_both_active(self):
        """Kill switch must fire when both drawdown and consecutive losses breach."""
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03, MAX_CONSECUTIVE_LOSSES=5)
        engine.update_account_state(equity=97_000, daily_pnl=-3_000)
        for _ in range(5):
            engine.record_trade_result(-200)
        assert engine.check_kill_switch() is True
        assert engine.is_kill_switch_active is True
        # Both downstream checks also blocked
        assert engine.validate_signal({}) is False
        assert engine.calculate_position_size(50.0, 45.0) == 0
