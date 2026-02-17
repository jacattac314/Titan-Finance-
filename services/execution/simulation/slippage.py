import random
import logging

logger = logging.getLogger("TitanSlippageModel")

class SlippageModel:
    """
    Simulates price slippage based on market volatility and order size.
    """
    def __init__(self, base_bps: int = 5):
        self.base_bps = base_bps # Basis points (1 bps = 0.01%)

    def calculate_price(self, decision_price: float, side: str, qty: float) -> float:
        """
        Returns the execution price including slippage.
        """
        if decision_price <= 0:
            return decision_price

        # Random walk component (Market noise)
        # Normal distribution, mean=0, std=1bps
        noise = random.gauss(0, 0.0001) 
        
        # Impact component (simplified)
        # Larger orders move price against you
        impact = (qty / 10000.0) * 0.00005 # Tiny impact per share
        
        slippage_pct = noise + impact + (self.base_bps / 10000.0)
        
        if side == "BUY":
            # Slippage increases buy price
            executed_price = decision_price * (1 + abs(slippage_pct))
        else:
            # Slippage decreases sell price
            executed_price = decision_price * (1 - abs(slippage_pct))
            
        return round(executed_price, 2)
