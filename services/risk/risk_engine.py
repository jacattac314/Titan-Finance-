import logging
import math

logger = logging.getLogger("TitanRisk")

class RiskEngine:
    def __init__(self, config: dict):
        self.max_daily_loss_pct = config.get("MAX_DAILY_LOSS_PCT", 0.03) # 3% hard stop
        self.risk_per_trade_pct = config.get("RISK_PER_TRADE_PCT", 0.01) # 1% per trade
        self.max_consecutive_losses = config.get("MAX_CONSECUTIVE_LOSSES", 5)
        
        self.starting_equity = 0.0
        self.current_equity = 0.0
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.is_kill_switch_active = False

    def update_account_state(self, equity: float, daily_pnl: float):
        """Update internal state from broker/db data."""
        self.current_equity = equity
        self.daily_pnl = daily_pnl
        
        if self.starting_equity == 0:
            self.starting_equity = equity - daily_pnl # Approximation if restart mid-day

    def check_kill_switch(self) -> bool:
        """
        Check if the Hard Kill Switch should be triggered.
        Returns True if trading should be HALTED.
        """
        if self.starting_equity <= 0: return False

        drawdown_pct = self.daily_pnl / self.starting_equity
        
        if drawdown_pct <= -self.max_daily_loss_pct:
            logger.critical(f"KILL SWITCH TRIGGERED: Drawdown {drawdown_pct:.2%} exceeds limit {self.max_daily_loss_pct:.2%}")
            self.is_kill_switch_active = True
            return True
            
        return False

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """
        Calculate position size using Fixed Fractional model.
        Units = (Equity * Risk%) / (Entry - Stop)
        """
        if self.is_kill_switch_active:
            return 0
            
        risk_amount = self.current_equity * self.risk_per_trade_pct
        risk_per_share = abs(entry_price - stop_loss)
        
        if risk_per_share == 0:
            logger.error("Invalid Stop Loss: Equal to Entry Price")
            return 0
            
        units = math.floor(risk_amount / risk_per_share)
        return units

    def validate_signal(self, signal: dict) -> bool:
        """
        Pass a signal through the Risk Governance layer.
        Returns True if signal is approved.
        """
        if self.is_kill_switch_active:
            logger.warning("Signal REJECTED: Kill Switch Active")
            return False
            
        # Add more checks: Spread size, Liquidity, etc.
        return True
