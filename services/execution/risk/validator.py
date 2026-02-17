import logging
from typing import Dict, Optional
from core.portfolio import VirtualPortfolio

logger = logging.getLogger("TitanOrderValidator")

class OrderValidator:
    """
    Enforces risk limits on outgoing orders.
    Acts as a pre-trade risk engine.
    """
    def __init__(self):
        self.MAX_ORDER_VALUE = 50000.0 # Max $ per trade
        self.MAX_CONCENTRATION = 0.20 # Max 20% of equity in one asset

    def validate(self, portfolio: VirtualPortfolio, symbol: str, signal_price: float, qty: float, side: str) -> bool:
        """
        Returns True if order is accepted, False if rejected.
        """
        if qty <= 0 or signal_price <= 0:
            logger.warning(f"REJECTED: Invalid qty/price ({qty} @ {signal_price})")
            return False

        # 1. Buying Power Check
        estimated_cost = qty * signal_price
        if side == "BUY":
            if portfolio.cash < estimated_cost:
                logger.warning(f"REJECTED: Insufficient Cash (Need ${estimated_cost:.2f}, Have ${portfolio.cash:.2f})")
                return False

        # 2. Max Order Value Check
        if estimated_cost > self.MAX_ORDER_VALUE:
            logger.warning(f"REJECTED: Order Value ${estimated_cost:.2f} exceeds limit ${self.MAX_ORDER_VALUE}")
            return False

        # 3. Concentration Check (Post-Trade)
        # Note: This requires knowing total equity. For MVP we use simplistic check.
        # Assuming we can get approx equity from portfolio.cash (if no positions) 
        # or we need a way to pass total_equity. 
        # For now, let's skip complex equity calc or pass it in? 
        # Let's trust portfolio.cash for simple initial check if all cash.
        
        # Improvement: Pass current_prices to calculate true equity?
        # For MVP, let's just guard against excessive single position size *if* we are buying.
        
        if side == "BUY":
            # If we buy this, will it exceed %?
            # Rough equity approx: Cash + Cost of this trade (since we convert cash to asset) + other assets
            # Let's just check if this single trade is > 20% of (Cash + Value)
            # Hard to do without real-time prices of other assets.
            # Simplified: Don't allow buying more than 20% of *current available cash*? No that's too restrictive.
            # Let's use a fixed "Max Position Size" of $25k for now?
            MAX_POS_SIZE = 25000.0
            existing_qty = portfolio.positions.get(symbol, {}).get('qty', 0)
            existing_val = existing_qty * signal_price
            new_val = existing_val + estimated_cost
            
            if new_val > MAX_POS_SIZE:
                 logger.warning(f"REJECTED: Position size ${new_val:.2f} would exceed limit ${MAX_POS_SIZE}")
                 return False

        return True
