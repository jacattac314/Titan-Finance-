import math
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
        Falls back to avg_price for positions without live quotes.
        """
        return self.calculate_total_equity({})

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
        
        if new_qty == 0:
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
            "remaining_cash": self.cash
        })

    def snapshot(self, current_prices: Dict[str, float]):
        """Record current equity for performance tracking."""
        equity = self.calculate_total_equity(current_prices)
        self.equity_curve.append({
            "timestamp": datetime.utcnow().isoformat(),
            "equity": equity,
            "cash": self.cash,
        })

    # ------------------------------------------------------------------
    # Risk-adjusted performance metrics
    # ------------------------------------------------------------------

    def max_drawdown(self) -> float:
        """
        Maximum peak-to-trough decline observed in the equity curve.
        Returns a value in [0, 1] (e.g. 0.15 = 15% drawdown).
        Returns 0.0 if fewer than 2 snapshots exist.
        """
        if len(self.equity_curve) < 2:
            return 0.0
        equities = [p["equity"] for p in self.equity_curve]
        peak = equities[0]
        max_dd = 0.0
        for equity in equities:
            if equity > peak:
                peak = equity
            if peak > 0:
                drawdown = (peak - equity) / peak
                if drawdown > max_dd:
                    max_dd = drawdown
        return round(max_dd, 4)

    def sortino_ratio(self) -> Optional[float]:
        """
        Annualised Sortino ratio (penalises only downside volatility).
        Requires at least 5 equity snapshots; returns None otherwise.
        Annualisation factor assumes ~252 trading periods per year.
        """
        if len(self.equity_curve) < 5:
            return None
        equities = [p["equity"] for p in self.equity_curve]
        returns = [
            (equities[i] - equities[i - 1]) / equities[i - 1]
            for i in range(1, len(equities))
            if equities[i - 1] > 0
        ]
        if not returns:
            return None
        mean_r = sum(returns) / len(returns)
        downside = [r for r in returns if r < 0]
        if not downside:
            return None
        downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
        if downside_std == 0:
            return None
        return round(mean_r / downside_std * math.sqrt(252), 4)

    def calmar_ratio(self) -> Optional[float]:
        """
        Calmar ratio: total return divided by maximum drawdown.
        Returns None when fewer than 2 snapshots exist or drawdown is zero.
        """
        if len(self.equity_curve) < 2:
            return None
        equities = [p["equity"] for p in self.equity_curve]
        if equities[0] <= 0:
            return None
        total_return = (equities[-1] - equities[0]) / equities[0]
        max_dd = self.max_drawdown()
        if max_dd == 0:
            return None
        return round(total_return / max_dd, 4)

    def performance_summary(self, current_prices: Dict[str, float]) -> Dict:
        """
        Return a complete performance snapshot suitable for the leaderboard
        payload.  Calls snapshot() so the current equity is always recorded.
        """
        self.snapshot(current_prices)
        return {
            "id": self.id,
            "cash": round(self.cash, 2),
            "equity": round(self.calculate_total_equity(current_prices), 2),
            "positions_count": len(self.positions),
            "total_return_pct": round(
                (self.calculate_total_equity(current_prices) - self.initial_cash)
                / self.initial_cash * 100, 2
            ) if self.initial_cash > 0 else 0.0,
            "max_drawdown_pct": round(self.max_drawdown() * 100, 2),
            "sortino_ratio": self.sortino_ratio(),
            "calmar_ratio": self.calmar_ratio(),
            "snapshot_count": len(self.equity_curve),
        }
