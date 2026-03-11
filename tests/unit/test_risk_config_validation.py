"""
Unit tests for the _load_and_validate_config() function in
services/risk/main.py

Verifies that:
  - Valid configurations pass without exiting.
  - Each out-of-range value triggers sys.exit(1).
  - Non-numeric values trigger sys.exit(1).
"""
import os
import sys
import pytest
import unittest.mock as mock

# _load_and_validate_config is defined at module level in risk/main.py;
# conftest.py already adds services/risk to sys.path.
from main import _load_and_validate_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_env(**overrides):
    """Return a minimal valid env-var mapping with optional overrides."""
    defaults = {
        "RISK_MAX_DAILY_LOSS": "0.03",
        "RISK_PER_TRADE": "0.01",
        "CIRCUIT_BREAKER_CONSECUTIVE_LOSSES": "5",
        "ROLLBACK_MIN_SHARPE": "0.5",
        "ROLLBACK_MIN_ACCURACY": "0.50",
    }
    defaults.update(overrides)
    return defaults


def load_with_env(**env_overrides):
    with mock.patch.dict(os.environ, make_env(**env_overrides), clear=False):
        # Remove any keys that the caller explicitly cleared by passing None
        env = make_env(**env_overrides)
        with mock.patch.dict(os.environ, env):
            return _load_and_validate_config()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestValidConfig:
    def test_default_values_pass(self):
        with mock.patch.dict(os.environ, make_env()):
            cfg = _load_and_validate_config()
        assert cfg["MAX_DAILY_LOSS_PCT"] == pytest.approx(0.03)
        assert cfg["RISK_PER_TRADE_PCT"] == pytest.approx(0.01)
        assert cfg["MAX_CONSECUTIVE_LOSSES"] == 5
        assert cfg["ROLLBACK_MIN_SHARPE"] == pytest.approx(0.5)
        assert cfg["ROLLBACK_MIN_ACCURACY"] == pytest.approx(0.50)

    def test_boundary_values_pass(self):
        """Values at the edges of the valid ranges must not exit."""
        env = make_env(
            RISK_MAX_DAILY_LOSS="0.001",
            RISK_PER_TRADE="0.0001",
            CIRCUIT_BREAKER_CONSECUTIVE_LOSSES="1",
            ROLLBACK_MIN_SHARPE="0.0",
            ROLLBACK_MIN_ACCURACY="0.0",
        )
        with mock.patch.dict(os.environ, env):
            cfg = _load_and_validate_config()
        assert cfg["MAX_DAILY_LOSS_PCT"] == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# Out-of-range values → sys.exit(1)
# ---------------------------------------------------------------------------

class TestInvalidRanges:
    def test_max_daily_loss_too_high(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(RISK_MAX_DAILY_LOSS="1.5")
        assert exc_info.value.code == 1

    def test_max_daily_loss_too_low(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(RISK_MAX_DAILY_LOSS="0.0")
        assert exc_info.value.code == 1

    def test_risk_per_trade_too_high(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(RISK_PER_TRADE="0.9")
        assert exc_info.value.code == 1

    def test_risk_per_trade_too_low(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(RISK_PER_TRADE="0.00001")
        assert exc_info.value.code == 1

    def test_consecutive_losses_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(CIRCUIT_BREAKER_CONSECUTIVE_LOSSES="0")
        assert exc_info.value.code == 1

    def test_rollback_accuracy_above_one(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(ROLLBACK_MIN_ACCURACY="1.1")
        assert exc_info.value.code == 1

    def test_rollback_sharpe_above_max(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(ROLLBACK_MIN_SHARPE="11.0")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Non-numeric values → sys.exit(1)
# ---------------------------------------------------------------------------

class TestNonNumericValues:
    def test_non_numeric_max_daily_loss(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(RISK_MAX_DAILY_LOSS="abc")
        assert exc_info.value.code == 1

    def test_non_numeric_consecutive_losses(self):
        with pytest.raises(SystemExit) as exc_info:
            load_with_env(CIRCUIT_BREAKER_CONSECUTIVE_LOSSES="five")
        assert exc_info.value.code == 1
