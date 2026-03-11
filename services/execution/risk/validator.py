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
            logger.warning(
                "Order rejected: %s",
                "zero_qty",
                extra={
                    "reason": "zero_qty",
                    "symbol": symbol,
                    "qty": qty,
                    "signal_price": signal_price,
                },
            )
            return False

        # 1. Buying Power Check
        estimated_cost = qty * signal_price
        if side == "BUY":
            if portfolio.cash < estimated_cost:
                logger.warning(
                    "Order rejected: %s",
                    "insufficient_cash",
                    extra={
                        "reason": "insufficient_cash",
                        "symbol": symbol,
                        "required": estimated_cost,
                        "available": portfolio.cash,
                    },
                )
                return False

        # 2. Max Order Value Check
        if estimated_cost > self.MAX_ORDER_VALUE:
            logger.warning(
                "Order rejected: %s",
                "order_value_exceeded",
                extra={
                    "reason": "order_value_exceeded",
                    "symbol": symbol,
                    "order_value": estimated_cost,
                    "max_order_value": self.MAX_ORDER_VALUE,
                },
            )
            return False

        # 3. Dynamic Concentration Check
        if side == "BUY":
            # Estimate total equity assuming other assets haven't moved massively from last fill price
            # (In a real system, we'd pass current_prices dict to calculate_total_equity)
            estimated_equity = portfolio.cash
            for pos_symbol, info in portfolio.positions.items():
                if pos_symbol == symbol:
                     # For the symbol being bought, value is existing + new cost
                     estimated_equity += (info.get('qty', 0) * signal_price)
                else:
                     # Approximation using avg_price or signal_price (rough)
                     estimated_equity += (info.get('qty', 0) * info.get('avg_price', 0))
            
            # The value of the specific position post-trade
            existing_qty = portfolio.positions.get(symbol, {}).get('qty', 0)
            existing_val = existing_qty * signal_price
            new_val = existing_val + estimated_cost
            
            # Use max concentration rule against the dynamically estimated equity
            max_pos_size = estimated_equity * self.MAX_CONCENTRATION
            
            if new_val > max_pos_size:
                logger.warning(
                    "Order rejected: %s",
                    "position_limit_exceeded",
                    extra={
                        "reason": "position_limit_exceeded",
                        "symbol": symbol,
                        "new_position_value": new_val,
                        "max_position_value": max_pos_size,
                    },
                )
                return False

        return True
