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
        # Performance tracking
        self.trades: int = 0
        self.closed_trades: int = 0
        self.wins: int = 0
        self.realized_pnl: float = 0.0

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

    def update_from_fill(self, fill_event: Dict):
        """
        Updates portfolio state based on a trade execution.
        fill_event: { "symbol": "AAPL", "qty": 10, "price": 150.0, "side": "buy", "timestamp": ... }
        """
        symbol = fill_event['symbol']
        qty = int(fill_event['qty']) # Positive for BUY? Or distinct side?
        price = float(fill_event['price'])
        side = fill_event['side'].lower()
        
        # Normalize quantity based on side if not already signed
        signed_qty = qty if side == 'buy' else -qty
        cost = signed_qty * price

        # Update Cash
        self.cash -= cost

        # Update Positions
        if symbol not in self.positions:
            self.positions[symbol] = {"qty": 0, "avg_price": 0.0}

        current_pos = self.positions[symbol]
        new_qty = current_pos['qty'] + signed_qty

        realized = 0.0
        if side == 'sell' and current_pos['qty'] > 0:
            realized = (price - current_pos['avg_price']) * abs(signed_qty)
            self.realized_pnl += realized
            self.closed_trades += 1
            if realized > 0:
                self.wins += 1

        if new_qty == 0:
            del self.positions[symbol]
        else:
            # Update avg price if buying
            if side == 'buy':
                total_cost = (current_pos['qty'] * current_pos['avg_price']) + cost
                current_pos['avg_price'] = total_cost / new_qty

            current_pos['qty'] = new_qty

        self.trades += 1

        # Log Trade
        self.history.append({
            "id": str(uuid.uuid4()),
            "timestamp": fill_event.get('timestamp', datetime.utcnow().isoformat()),
            "symbol": symbol,
            "side": side,
            "qty": abs(signed_qty),
            "price": price,
            "remaining_cash": self.cash
        })

    def snapshot(self, current_prices: Dict[str, float]) -> Dict:
        """Record current equity and return a rich summary dict."""
        equity = self.calculate_total_equity(current_prices)
        pnl = equity - self.initial_cash
        win_rate = (self.wins / self.closed_trades * 100.0) if self.closed_trades else 0.0
        snap = {
            "timestamp": datetime.utcnow().isoformat(),
            "equity": round(equity, 2),
            "cash": round(self.cash, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / self.initial_cash) * 100.0, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "trades": self.trades,
            "closed_trades": self.closed_trades,
            "wins": self.wins,
            "win_rate": round(win_rate, 2),
            "open_positions": len(self.positions),
        }
        self.equity_curve.append(snap)
        return snap
