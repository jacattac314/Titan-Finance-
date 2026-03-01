from datetime import datetime
from typing import Dict, List, Optional
import uuid

class VirtualPortfolio:
    """
    Represents an isolated portfolio for a specific strategy/model.
    Tracks cash, positions, and equity curve independently of the master account.
    """
    def __init__(self, portfolio_id: str, starting_cash: float = 100000.0):
        self.id = portfolio_id
        self.cash = starting_cash
        self.initial_cash = starting_cash
        self.positions: Dict[str, Dict] = {} # { "AAPL": { "qty": 10, "avg_price": 150.0 } }
        self.equity_curve: List[Dict] = [] # [{ "timestamp": "...", "equity": 100000.0 }]
        self.history: List[Dict] = [] # Trade history

    @property
    def total_equity(self) -> float:
        """
        Calculates total equity (Cash + Market Value of Positions).
        Note: Needs current market prices to be accurate. 
        For MVP, we might estimate or require an update method.
        """
        # value = self.cash + sum(p['qty'] * current_price for p in positions)
        return self.cash # Placeholder until we pass in current prices

    def get_market_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate market value of positions based on latest prices."""
        value = 0.0
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos['avg_price']) # Fallback to avg_price if real-time missing
            value += pos['qty'] * price
        return value

    def calculate_total_equity(self, current_prices: Dict[str, float]) -> float:
        return self.cash + self.get_market_value(current_prices)

    def can_afford(self, symbol: str, qty: int, price: float) -> bool:
        """Check if portfolio has enough cash for the trade."""
        cost = qty * price
        # Simple long-only check for MVP
        if qty > 0:
            return self.cash >= cost
        return True # Selling adds cash (presumed)

    def update_from_fill(self, fill_event: Dict) -> float:
        """
        Updates portfolio state based on a trade execution.
        Returns the realized PnL of the fill event (if any).
        fill_event: { "symbol": "AAPL", "qty": 10, "price": 150.0, "side": "buy", "timestamp": ... }
        """
        symbol = fill_event['symbol']
        qty = int(fill_event['qty']) # Positive for BUY? Or distinct side?
        price = float(fill_event['price'])
        side = fill_event['side'].lower()
        
        # Normalize quantity based on side if not already signed
        signed_qty = qty if side == 'buy' else -qty
        cost = signed_qty * price

        realized_pnl = 0.0

        # Update Cash
        self.cash -= cost

        # Update Positions
        if symbol not in self.positions:
            self.positions[symbol] = {"qty": 0, "avg_price": 0.0}
        
        current_pos = self.positions[symbol]
        
        if side == 'sell' and current_pos['qty'] > 0:
            # Calculate realized PnL: (Exit Price - Entry Price) * qty sold
            # We assume we don't sell more than we have for now, or if we do, it's just closing the long.
            qty_sold = min(qty, current_pos['qty'])
            realized_pnl = (price - current_pos['avg_price']) * qty_sold

        new_qty = current_pos['qty'] + signed_qty
        
        if new_qty <= 0:
            if symbol in self.positions:
                del self.positions[symbol]
        else:
            # Update avg price if buying
            if side == 'buy':
                total_cost = (current_pos['qty'] * current_pos['avg_price']) + cost
                current_pos['avg_price'] = total_cost / new_qty
            
            current_pos['qty'] = new_qty
            
        # Log Trade
        self.history.append({
            "id": str(uuid.uuid4()),
            "timestamp": fill_event.get('timestamp', datetime.utcnow().isoformat()),
            "symbol": symbol,
            "side": side,
            "qty": abs(signed_qty),
            "price": price,
            "remaining_cash": self.cash,
            "realized_pnl": realized_pnl
        })
        
        return realized_pnl

    def snapshot(self, current_prices: Dict[str, float]):
        """Record current equity for performance tracking."""
        equity = self.calculate_total_equity(current_prices)
        self.equity_curve.append({
            "timestamp": datetime.utcnow().isoformat(),
            "equity": equity,
            "cash": self.cash
        })
