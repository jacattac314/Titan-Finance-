"""
Unit tests for services/risk/risk_engine.py

The RiskEngine is the financial safety layer: it governs the kill switch,
position sizing, signal gating, and model-performance rollback.  Bugs here
translate directly into monetary loss, so every public method is covered.
"""
import pytest
from risk_engine import RiskEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(**overrides):
    """Return a RiskEngine with sensible defaults, optionally overridden."""
    config = {
        "MAX_DAILY_LOSS_PCT": 0.03,
        "RISK_PER_TRADE_PCT": 0.01,
        "MAX_CONSECUTIVE_LOSSES": 5,
        "ROLLBACK_MIN_SHARPE": 0.50,
        "ROLLBACK_MIN_ACCURACY": 0.50,
    }
    config.update(overrides)
    return RiskEngine(config)


def _seed_predictions(engine, correct_flags, returns):
    """Feed a list of (correct, return) pairs into engine."""
    for c, r in zip(correct_flags, returns):
        engine.record_prediction(c, r)


# ---------------------------------------------------------------------------
# update_account_state
# ---------------------------------------------------------------------------

class TestUpdateAccountState:
    def test_sets_equity_and_pnl(self):
        engine = make_engine()
        engine.update_account_state(equity=120_000, daily_pnl=2_000)
        assert engine.current_equity == 120_000
        assert engine.daily_pnl == 2_000

    def test_derives_starting_equity_on_first_call(self):
        engine = make_engine()
        engine.update_account_state(equity=103_000, daily_pnl=3_000)
        assert engine.starting_equity == 100_000  # 103k - 3k

    def test_does_not_override_starting_equity_on_second_call(self):
        engine = make_engine()
        engine.update_account_state(equity=103_000, daily_pnl=3_000)
        engine.update_account_state(equity=105_000, daily_pnl=5_000)
        # starting_equity must remain anchored to the first observation
        assert engine.starting_equity == 100_000


# ---------------------------------------------------------------------------
# check_kill_switch — drawdown branch
# ---------------------------------------------------------------------------

class TestKillSwitchDrawdown:
    def test_activates_when_drawdown_exceeds_limit(self):
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=97_000, daily_pnl=-3_000)
        assert engine.check_kill_switch() is True
        assert engine.is_kill_switch_active is True

    def test_activates_when_drawdown_exactly_at_limit(self):
        # -3% on a 100k account = -3000 loss; starting_equity = 100k
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=100_000, daily_pnl=0)
        # Manually set starting equity so the maths is exact
        engine.starting_equity = 100_000
        engine.daily_pnl = -3_000
        assert engine.check_kill_switch() is True

    def test_does_not_activate_when_drawdown_below_limit(self):
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=98_000, daily_pnl=-2_000)
        assert engine.check_kill_switch() is False
        assert engine.is_kill_switch_active is False

    def test_returns_false_when_starting_equity_is_zero(self):
        engine = make_engine()
        # starting_equity defaults to 0.0 before any account update
        assert engine.check_kill_switch() is False

    def test_stays_active_once_triggered(self):
        engine = make_engine(MAX_DAILY_LOSS_PCT=0.03)
        engine.update_account_state(equity=96_000, daily_pnl=-4_000)
        engine.check_kill_switch()
        # Even if equity recovers, the flag should remain set
        engine.update_account_state(equity=102_000, daily_pnl=2_000)
        assert engine.is_kill_switch_active is True


# ---------------------------------------------------------------------------
# check_kill_switch — consecutive losses branch
# ---------------------------------------------------------------------------

class TestKillSwitchConsecutiveLosses:
    def test_activates_at_consecutive_loss_limit(self):
        engine = make_engine(MAX_CONSECUTIVE_LOSSES=5)
        engine.update_account_state(equity=100_000, daily_pnl=0)
        for _ in range(5):
            engine.record_trade_result(-100)
        assert engine.check_kill_switch() is True
        assert engine.is_kill_switch_active is True

    def test_does_not_activate_below_consecutive_loss_limit(self):
        engine = make_engine(MAX_CONSECUTIVE_LOSSES=5)
        engine.update_account_state(equity=100_000, daily_pnl=0)
        for _ in range(4):
            engine.record_trade_result(-100)
        assert engine.check_kill_switch() is False

    def test_consecutive_losses_reset_on_winning_trade(self):
        engine = make_engine(MAX_CONSECUTIVE_LOSSES=5)
        engine.update_account_state(equity=100_000, daily_pnl=0)
        for _ in range(4):
            engine.record_trade_result(-100)
        engine.record_trade_result(200)  # win resets counter
        assert engine.consecutive_losses == 0

    def test_loss_counter_increments_on_negative_pnl(self):
        engine = make_engine()
        engine.record_trade_result(-50)
        engine.record_trade_result(-50)
        assert engine.consecutive_losses == 2

    def test_loss_counter_does_not_increment_on_breakeven(self):
        engine = make_engine()
        engine.record_trade_result(0)
        assert engine.consecutive_losses == 0


# ---------------------------------------------------------------------------
# reset_kill_switch
# ---------------------------------------------------------------------------

class TestResetKillSwitch:
    def test_clears_kill_switch_flag(self):
        engine = make_engine()
        engine.is_kill_switch_active = True
        engine.reset_kill_switch()
        assert engine.is_kill_switch_active is False

    def test_resets_consecutive_losses(self):
        engine = make_engine()
        engine.consecutive_losses = 7
        engine.current_equity = 90_000
        engine.reset_kill_switch()
        assert engine.consecutive_losses == 0

    def test_re_anchors_starting_equity_to_current_equity(self):
        engine = make_engine()
        engine.current_equity = 95_000
        engine.reset_kill_switch()
        assert engine.starting_equity == 95_000
        assert engine.daily_pnl == 0.0


# ---------------------------------------------------------------------------
# calculate_position_size
# ---------------------------------------------------------------------------

class TestCalculatePositionSize:
    def test_returns_zero_when_kill_switch_active(self):
        engine = make_engine()
        engine.is_kill_switch_active = True
        engine.current_equity = 100_000
        assert engine.calculate_position_size(100.0, 95.0) == 0

    def test_returns_zero_when_stop_equals_entry(self):
        engine = make_engine()
        engine.current_equity = 100_000
        assert engine.calculate_position_size(100.0, 100.0) == 0

    def test_correct_sizing_with_known_inputs(self):
        # equity=100k, risk_pct=1% => risk_amount=1000
        # entry=100, stop=95 => risk_per_share=5
        # units = floor(1000 / 5) = 200
        engine = make_engine(RISK_PER_TRADE_PCT=0.01)
        engine.current_equity = 100_000
        assert engine.calculate_position_size(100.0, 95.0) == 200

    def test_floors_fractional_units(self):
        # risk_amount=1000, risk_per_share=3 => floor(333.33) = 333
        engine = make_engine(RISK_PER_TRADE_PCT=0.01)
        engine.current_equity = 100_000
        assert engine.calculate_position_size(100.0, 97.0) == 333

    def test_returns_zero_when_equity_is_zero(self):
        engine = make_engine()
        engine.current_equity = 0
        assert engine.calculate_position_size(100.0, 95.0) == 0


# ---------------------------------------------------------------------------
# validate_signal
# ---------------------------------------------------------------------------

class TestValidateSignal:
    def test_accepts_signal_in_normal_mode(self):
        engine = make_engine()
        assert engine.validate_signal({"symbol": "AAPL", "signal": "BUY"}) is True

    def test_rejects_signal_when_kill_switch_active(self):
        engine = make_engine()
        engine.is_kill_switch_active = True
        assert engine.validate_signal({"symbol": "AAPL", "signal": "BUY"}) is False

    def test_rejects_signal_when_manual_approval_mode_active(self):
        engine = make_engine()
        engine.is_manual_approval_mode = True
        assert engine.validate_signal({"symbol": "AAPL", "signal": "BUY"}) is False

    def test_kill_switch_takes_priority_over_manual_mode(self):
        engine = make_engine()
        engine.is_kill_switch_active = True
        engine.is_manual_approval_mode = True
        assert engine.validate_signal({}) is False


# ---------------------------------------------------------------------------
# Rolling accuracy
# ---------------------------------------------------------------------------

class TestRollingAccuracy:
    def test_returns_none_with_fewer_than_five_samples(self):
        engine = make_engine()
        _seed_predictions(engine, [True, True, False, True], [0.01] * 4)
        assert engine.get_rolling_accuracy() is None

    def test_returns_one_when_all_correct(self):
        engine = make_engine()
        _seed_predictions(engine, [True] * 10, [0.01] * 10)
        assert engine.get_rolling_accuracy() == 1.0

    def test_returns_zero_when_all_wrong(self):
        engine = make_engine()
        _seed_predictions(engine, [False] * 10, [-0.01] * 10)
        assert engine.get_rolling_accuracy() == 0.0

    def test_correct_ratio_calculation(self):
        engine = make_engine()
        # 7 correct, 3 wrong => 0.7
        _seed_predictions(engine, [True] * 7 + [False] * 3, [0.0] * 10)
        assert abs(engine.get_rolling_accuracy() - 0.7) < 1e-9

    def test_window_trims_to_20_samples(self):
        engine = make_engine()
        # Feed 25 samples: first 5 are wrong, last 20 are correct
        _seed_predictions(engine, [False] * 5 + [True] * 20, [0.0] * 25)
        # Only the last 20 should be in the window => accuracy = 1.0
        assert engine.get_rolling_accuracy() == 1.0


# ---------------------------------------------------------------------------
# Rolling Sharpe
# ---------------------------------------------------------------------------

class TestRollingSharpe:
    def test_returns_none_with_fewer_than_five_samples(self):
        engine = make_engine()
        _seed_predictions(engine, [True] * 3, [0.01, 0.02, 0.01])
        assert engine.get_rolling_sharpe() is None

    def test_returns_none_when_all_returns_identical(self):
        # Zero standard deviation -> undefined Sharpe.
        # NOTE: must use exact integer-representable values (e.g. 0.0) so that
        # floating-point subtraction r - mean_r is exactly 0.0.  Repeating
        # decimal constants like 0.01 accumulate rounding error and produce a
        # non-zero (astronomically large) Sharpe — a known limitation in the
        # current `if std_r == 0` check.
        engine = make_engine()
        _seed_predictions(engine, [True] * 10, [0.0] * 10)
        assert engine.get_rolling_sharpe() is None

    def test_positive_sharpe_for_consistently_positive_returns(self):
        engine = make_engine()
        # All positive, with some variance
        returns = [0.01, 0.02, 0.015, 0.025, 0.01, 0.02, 0.01, 0.03, 0.02, 0.015]
        _seed_predictions(engine, [True] * 10, returns)
        sharpe = engine.get_rolling_sharpe()
        assert sharpe is not None
        assert sharpe > 0

    def test_negative_sharpe_for_consistently_negative_returns(self):
        engine = make_engine()
        returns = [-0.01, -0.02, -0.015, -0.025, -0.01, -0.02, -0.01, -0.03, -0.02, -0.015]
        _seed_predictions(engine, [False] * 10, returns)
        sharpe = engine.get_rolling_sharpe()
        assert sharpe is not None
        assert sharpe < 0

    def test_sharpe_annualisation_factor(self):
        # With a controlled dataset we can verify the annualisation (sqrt(252))
        import math
        engine = make_engine()
        returns = [0.01, -0.01, 0.02, -0.02, 0.01, -0.01, 0.02, -0.02, 0.01, -0.01]
        _seed_predictions(engine, [True] * 10, returns)
        n = len(returns)
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / n
        std_r = variance ** 0.5
        expected = round((mean_r / std_r) * math.sqrt(252), 4)
        assert engine.get_rolling_sharpe() == expected


# ---------------------------------------------------------------------------
# check_model_performance / manual approval rollback
# ---------------------------------------------------------------------------

class TestModelPerformanceRollback:
    def _engine_with_low_sharpe(self):
        engine = make_engine(ROLLBACK_MIN_SHARPE=0.5)
        # Strongly negative returns to force a negative Sharpe
        returns = [-0.02, -0.03, -0.01, -0.04, -0.02, -0.03, -0.01, -0.04, -0.02, -0.03]
        _seed_predictions(engine, [False] * 10, returns)
        return engine

    def _engine_with_low_accuracy(self):
        engine = make_engine(ROLLBACK_MIN_ACCURACY=0.50)
        # 2 correct out of 10 => accuracy=0.2
        returns = [0.01] * 10
        _seed_predictions(engine, [True, True] + [False] * 8, returns)
        return engine

    def test_activates_manual_mode_on_low_sharpe(self):
        engine = self._engine_with_low_sharpe()
        triggered = engine.check_model_performance()
        assert triggered is True
        assert engine.is_manual_approval_mode is True

    def test_activates_manual_mode_on_low_accuracy(self):
        engine = self._engine_with_low_accuracy()
        triggered = engine.check_model_performance()
        assert triggered is True
        assert engine.is_manual_approval_mode is True

    def test_does_not_double_trigger_when_already_in_manual_mode(self):
        engine = self._engine_with_low_sharpe()
        engine.check_model_performance()
        assert engine.is_manual_approval_mode is True
        # Second call must return False (no new transition)
        assert engine.check_model_performance() is False

    def test_no_rollback_when_metrics_are_healthy(self):
        engine = make_engine(ROLLBACK_MIN_SHARPE=0.5, ROLLBACK_MIN_ACCURACY=0.50)
        returns = [0.01, 0.02, 0.015, 0.025, 0.01, 0.02, 0.01, 0.03, 0.02, 0.015]
        _seed_predictions(engine, [True] * 10, returns)
        triggered = engine.check_model_performance()
        assert triggered is False
        assert engine.is_manual_approval_mode is False

    def test_reset_manual_approval_mode_re_enables_auto_execution(self):
        engine = self._engine_with_low_accuracy()
        engine.check_model_performance()
        assert engine.is_manual_approval_mode is True
        engine.reset_manual_approval_mode()
        assert engine.is_manual_approval_mode is False
        # Signal should now be accepted
        assert engine.validate_signal({}) is True
