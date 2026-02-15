from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class Position:
    qty: float = 0.0
    avg_cost: float = 0.0


@dataclass
class TradeFill:
    symbol: str
    side: str
    qty: float
    price: float
    realized_pnl: float = 0.0


class VirtualPortfolio:
    """In-memory portfolio ledger for one model."""

    def __init__(self, model_id: str, model_name: str, starting_cash: float):
        self.model_id = model_id
        self.model_name = model_name
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions: Dict[str, Position] = {}
        self.trades = 0
        self.closed_trades = 0
        self.wins = 0
        self.realized_pnl = 0.0

    def mark_to_market(self, last_prices: Dict[str, float]) -> float:
        total = self.cash
        for symbol, position in self.positions.items():
            if position.qty <= 0:
                continue
            price = last_prices.get(symbol, position.avg_cost)
            total += position.qty * price
        return total

    def buy(self, symbol: str, price: float, budget: float) -> Optional[TradeFill]:
        if price <= 0 or budget <= 0:
            return None

        budget = min(budget, self.cash)
        qty = int(budget / price)
        if qty <= 0:
            return None

        cost = qty * price
        if cost > self.cash:
            return None

        position = self.positions.get(symbol, Position())
        new_qty = position.qty + qty
        if new_qty > 0:
            position.avg_cost = ((position.avg_cost * position.qty) + cost) / new_qty
        position.qty = new_qty
        self.positions[symbol] = position

        self.cash -= cost
        self.trades += 1
        return TradeFill(symbol=symbol, side="BUY", qty=qty, price=price)

    def sell(self, symbol: str, price: float, qty: Optional[float] = None) -> Optional[TradeFill]:
        if price <= 0:
            return None

        position = self.positions.get(symbol)
        if not position or position.qty <= 0:
            return None

        if qty is None or qty > position.qty:
            qty = position.qty
        if qty <= 0:
            return None

        proceeds = qty * price
        realized_pnl = (price - position.avg_cost) * qty

        position.qty -= qty
        if position.qty <= 0:
            position.qty = 0.0
            position.avg_cost = 0.0
        self.positions[symbol] = position

        self.cash += proceeds
        self.realized_pnl += realized_pnl
        self.trades += 1
        self.closed_trades += 1
        if realized_pnl > 0:
            self.wins += 1

        return TradeFill(
            symbol=symbol,
            side="SELL",
            qty=qty,
            price=price,
            realized_pnl=realized_pnl,
        )

    def snapshot(self, last_prices: Dict[str, float]) -> dict:
        equity = self.mark_to_market(last_prices)
        pnl = equity - self.starting_cash
        win_rate = (self.wins / self.closed_trades * 100.0) if self.closed_trades else 0.0
        open_positions = len([p for p in self.positions.values() if p.qty > 0])
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / self.starting_cash) * 100.0, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "trades": self.trades,
            "wins": self.wins,
            "closed_trades": self.closed_trades,
            "win_rate": round(win_rate, 2),
            "open_positions": open_positions,
        }


class VirtualPortfolioManager:
    """Owns multiple virtual portfolios so many models can share one live data stream."""

    def __init__(
        self,
        starting_cash: float = 100000.0,
        risk_per_trade: float = 0.10,
        min_confidence: float = 0.25,
        max_models: int = 10,
    ):
        self.starting_cash = starting_cash
        self.risk_per_trade = risk_per_trade
        self.min_confidence = min_confidence
        self.max_models = max_models
        self.portfolios: Dict[str, VirtualPortfolio] = {}
        self.last_prices: Dict[str, float] = {}

    def update_price(self, symbol: str, price: float):
        if symbol and price > 0:
            self.last_prices[symbol] = price

    def _get_or_create_portfolio(self, model_id: str, model_name: str) -> Optional[VirtualPortfolio]:
        portfolio = self.portfolios.get(model_id)
        if portfolio:
            return portfolio

        if len(self.portfolios) >= self.max_models:
            return None

        portfolio = VirtualPortfolio(
            model_id=model_id,
            model_name=model_name,
            starting_cash=self.starting_cash,
        )
        self.portfolios[model_id] = portfolio
        return portfolio

    def apply_signal(self, signal: dict) -> Optional[Tuple[VirtualPortfolio, TradeFill]]:
        side = signal.get("signal")
        if side not in {"BUY", "SELL"}:
            return None

        symbol = signal.get("symbol")
        if not symbol:
            return None

        model_id = signal.get("model_id", "legacy_model")
        model_name = signal.get("model_name", model_id)
        portfolio = self._get_or_create_portfolio(model_id, model_name)
        if not portfolio:
            return None

        confidence = max(float(signal.get("confidence", 0.0)), self.min_confidence)
        price = float(self.last_prices.get(symbol) or signal.get("price") or 0.0)
        if price <= 0:
            return None

        if side == "BUY":
            equity = portfolio.mark_to_market(self.last_prices)
            budget = min(portfolio.cash, equity * self.risk_per_trade * confidence)
            fill = portfolio.buy(symbol=symbol, price=price, budget=budget)
        else:
            fill = portfolio.sell(symbol=symbol, price=price)

        if not fill:
            return None

        return portfolio, fill

    def leaderboard(self) -> list:
        snapshots = [p.snapshot(self.last_prices) for p in self.portfolios.values()]
        snapshots.sort(key=lambda row: row["pnl"], reverse=True)
        return snapshots
