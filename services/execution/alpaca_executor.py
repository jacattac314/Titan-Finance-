import logging
import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

logger = logging.getLogger("TitanExecutor")

class AlpacaExecutor:
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.paper = True # Default to paper for safety
        
        if not self.api_key:
            raise ValueError("ALPACA_API_KEY not found")
            
        self.client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        logger.info(f"Initialized AlpacaExecutor (Paper={self.paper})")

    async def get_account(self):
        """Fetch current account info (Equity, Buying Power)."""
        return self.client.get_account()

    async def submit_order(self, symbol: str, qty: float, side: str, order_type: str = 'market', limit_price: float = None):
        """
        Submit an order to Alpaca.
        Args:
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
        """
        side_enum = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        
        req = None
        if order_type == 'market':
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side_enum,
                time_in_force=TimeInForce.DAY
            )
        elif order_type == 'limit':
            if limit_price is None:
                raise ValueError("Limit Price required for Limit Orders")
            req = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side_enum,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price
            )
            
        try:
            order = self.client.submit_order(req)
            logger.info(f"Order Submitted: {order.id} | {side} {qty} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Order Submission Failed: {e}")
            raise

    async def liquidate_all(self):
        """Emergency EOD or Kill Switch Liquidation."""
        logger.warning("LIQUIDATING ALL POSITIONS")
        try:
            self.client.close_all_positions(cancel_orders=True)
        except Exception as e:
            logger.error(f"Liquidation Failed: {e}")
