import random
import logging
import math

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

        # Baseline noise (Normal distribution) + Volatility spike (Pareto distribution)
        # Using Pareto allows "long-tail" high slippage events
        normal_noise = random.gauss(0, 0.0001)
        volatility_spike = (random.paretovariate(3.0) - 1.0) * 0.0002
        noise = normal_noise + volatility_spike
        
        # Impact component: Square Root Law of Market Impact
        # Larger orders move price against you non-linearly
        impact = math.sqrt(qty / 10000.0) * 0.00005 
        
        slippage_pct = noise + impact + (self.base_bps / 10000.0)
        
        if side == "BUY":
            # Slippage increases buy price
            executed_price = decision_price * (1 + abs(slippage_pct))
        else:
            # Slippage decreases sell price
            executed_price = decision_price * (1 - abs(slippage_pct))
            
        return round(executed_price, 2)
