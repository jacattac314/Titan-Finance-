"""
RiskEngine — Core risk governance layer for Titan Finance.

Responsibilities:
    1. Kill Switch         — halts all trading when daily drawdown exceeds limit.
    2. Position Sizing     — Fixed Fractional model scaled by risk_per_trade_pct.
    3. Signal Validation   — Pre-execution gate checked before every order.
    4. Manual Approval Mode— Rollback triggered when model Sharpe or accuracy
                             falls below configured thresholds.  In this mode
                             signals are logged but NOT auto-executed.

Configuration (env vars / config dict):
    MAX_DAILY_LOSS_PCT          float  default 0.03  (3 %)
    RISK_PER_TRADE_PCT          float  default 0.01  (1 %)
    MAX_CONSECUTIVE_LOSSES      int    default 5
    ROLLBACK_MIN_SHARPE         float  default 0.5
    ROLLBACK_MIN_ACCURACY       float  default 0.50  (50 %)
"""

import logging
import math
from typing import List, Optional

logger = logging.getLogger("TitanRisk")


class RiskEngine:
    def __init__(self, config: dict):
        # --- Circuit-breaker thresholds ---
        self.max_daily_loss_pct: float = config.get("MAX_DAILY_LOSS_PCT", 0.03)
        self.max_consecutive_losses: int = int(config.get("MAX_CONSECUTIVE_LOSSES", 5))

        # --- Position sizing ---
        self.risk_per_trade_pct: float = config.get("RISK_PER_TRADE_PCT", 0.01)

        # --- Model-performance rollback thresholds ---
        self.rollback_min_sharpe: float = config.get("ROLLBACK_MIN_SHARPE", 0.50)
        self.rollback_min_accuracy: float = config.get("ROLLBACK_MIN_ACCURACY", 0.50)

        # --- Account state ---
        self.starting_equity: float = 0.0
        self.current_equity: float = 0.0
        self.daily_pnl: float = 0.0
        self.consecutive_losses: int = 0

        # --- Model performance tracking (rolling window) ---
        self._recent_predictions: List[bool] = []   # True=correct, False=wrong
        self._recent_returns: List[float] = []       # trade return percentages
        self._window_size: int = 20                  # rolling window for metrics

        # --- Control flags ---
        self.is_kill_switch_active: bool = False
        self.is_manual_approval_mode: bool = False

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------

    def update_account_state(self, equity: float, daily_pnl: float) -> None:
        """
        Refresh internal state from broker or portfolio data.
        Should be called on every account poll cycle.
        """
        self.current_equity = equity
        self.daily_pnl = daily_pnl

        if self.starting_equity == 0:
            # Approximate start-of-day equity when engine restarts mid-session
            self.starting_equity = equity - daily_pnl

    # ------------------------------------------------------------------
    # Kill switch (circuit breaker)
    # ------------------------------------------------------------------

    def check_kill_switch(self) -> bool:
        """
        Evaluate whether trading should be hard-halted.

        Returns True (and activates the switch) when:
            • Daily drawdown exceeds max_daily_loss_pct, OR
            • Consecutive losses exceed max_consecutive_losses.
        """
        if self.starting_equity <= 0:
            return False

        drawdown_pct = self.daily_pnl / self.starting_equity

        # Drawdown threshold
        if drawdown_pct <= -self.max_daily_loss_pct:
            logger.critical(
                f"KILL SWITCH: Daily drawdown {drawdown_pct:.2%} exceeds "
                f"limit -{self.max_daily_loss_pct:.2%}."
            )
            self.is_kill_switch_active = True
            return True

        # Consecutive loss threshold
        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.critical(
                f"KILL SWITCH: {self.consecutive_losses} consecutive losses "
                f"exceeds limit {self.max_consecutive_losses}."
            )
            self.is_kill_switch_active = True
            return True

        return False

    def record_trade_result(self, pnl: float) -> None:
        """
        Record the outcome of a closed trade.
        Used to maintain the consecutive-loss counter.
        """
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """
        Fixed-Fractional position sizing.
            Units = floor( equity × risk_per_trade_pct / risk_per_share )

        Returns 0 if the kill switch is active or inputs are invalid.
        """
        if self.is_kill_switch_active:
            return 0

        risk_amount = self.current_equity * self.risk_per_trade_pct
        risk_per_share = abs(entry_price - stop_loss)

        if risk_per_share == 0:
            logger.error("Invalid stop_loss: equal to entry_price. Returning 0.")
            return 0

        return math.floor(risk_amount / risk_per_share)

    # ------------------------------------------------------------------
    # Signal validation
    # ------------------------------------------------------------------

    def validate_signal(self, signal: dict) -> bool:
        """
        Pass a signal through the risk governance layer.

        Returns False (and logs reason) if the signal should be suppressed.
        """
        if self.is_kill_switch_active:
            logger.warning("Signal REJECTED — kill switch active.")
            return False

        if self.is_manual_approval_mode:
            logger.info(
                "Signal QUEUED — manual approval mode active. "
                "Auto-execution suspended pending model review."
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Model performance monitoring → Manual Approval rollback
    # ------------------------------------------------------------------

    def record_prediction(self, correct: bool, trade_return_pct: float) -> None:
        """
        Log a single prediction outcome into the rolling performance window.

        Args:
            correct:           True if the model's directional prediction was right.
            trade_return_pct:  Actual return of the trade (signed, e.g. -0.012 = -1.2%).
        """
        self._recent_predictions.append(correct)
        self._recent_returns.append(trade_return_pct)

        # Trim to window
        if len(self._recent_predictions) > self._window_size:
            self._recent_predictions.pop(0)
        if len(self._recent_returns) > self._window_size:
            self._recent_returns.pop(0)

    def get_rolling_accuracy(self) -> Optional[float]:
        """
        Return rolling directional accuracy, or None if insufficient data.
        """
        if len(self._recent_predictions) < 5:
            return None
        return sum(self._recent_predictions) / len(self._recent_predictions)

    def get_rolling_sharpe(self) -> Optional[float]:
        """
        Return annualised Sharpe ratio over the rolling window.
        Assumes daily returns; annualisation factor = sqrt(252).
        Returns None if insufficient data or zero volatility.
        """
        if len(self._recent_returns) < 5:
            return None

        n = len(self._recent_returns)
        mean_r = sum(self._recent_returns) / n
        variance = sum((r - mean_r) ** 2 for r in self._recent_returns) / n
        std_r = variance ** 0.5

        if std_r == 0:
            return None

        sharpe = (mean_r / std_r) * (252 ** 0.5)
        return round(sharpe, 4)

    def check_model_performance(self) -> bool:
        """
        Evaluate rolling model metrics and activate manual approval mode
        if Sharpe or accuracy drops below configured thresholds.

        Returns True if manual approval mode was (newly) activated.
        Should be called periodically (e.g. every N trades or on a timer).
        """
        if self.is_manual_approval_mode:
            return False  # Already in rollback state; no change.

        sharpe = self.get_rolling_sharpe()
        accuracy = self.get_rolling_accuracy()

        triggered = False
        reason = ""

        if sharpe is not None and sharpe < self.rollback_min_sharpe:
            reason = (
                f"Rolling Sharpe {sharpe:.2f} below threshold "
                f"{self.rollback_min_sharpe:.2f}."
            )
            triggered = True

        if accuracy is not None and accuracy < self.rollback_min_accuracy:
            reason += (
                f" Rolling accuracy {accuracy:.1%} below threshold "
                f"{self.rollback_min_accuracy:.1%}."
            )
            triggered = True

        if triggered:
            self.is_manual_approval_mode = True
            logger.warning(
                f"MODEL ROLLBACK — switching to manual approval mode. {reason}"
            )

        return triggered

    def reset_manual_approval_mode(self) -> None:
        """
        Re-enable auto-execution after manual review confirms model health.
        This should require an explicit operator action in production.
        """
        self.is_manual_approval_mode = False
        logger.info("Manual approval mode reset. Auto-execution resumed.")

    def reset_kill_switch(self) -> None:
        """
        Clear the kill switch after an operator has reviewed and authorised resume.
        Resets starting_equity and daily_pnl counters for the new session.
        """
        self.is_kill_switch_active = False
        self.consecutive_losses = 0
        self.starting_equity = self.current_equity
        self.daily_pnl = 0.0
        logger.warning("Kill switch reset. Starting equity anchored to current equity.")
