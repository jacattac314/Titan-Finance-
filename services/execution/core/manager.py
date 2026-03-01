from typing import Dict, List, Optional
import logging
from .portfolio import VirtualPortfolio

logger = logging.getLogger("TitanPortfolioManager")

class PortfolioManager:
    """
    Orchestrates multiple VirtualPortfolio instances.
    Routes execution fills to the correct portfolio based on order ID or strategy tag.
    """
    def __init__(self):
        self.portfolios: Dict[str, VirtualPortfolio] = {}
        self.order_map: Dict[str, str] = {} # order_id -> portfolio_id

    def create_portfolio(self, portfolio_id: str, starting_cash: float = 100000.0) -> VirtualPortfolio:
        if portfolio_id in self.portfolios:
            logger.warning(f"Portfolio {portfolio_id} already exists.")
            return self.portfolios[portfolio_id]
        
        vp = VirtualPortfolio(portfolio_id, starting_cash)
        self.portfolios[portfolio_id] = vp
        logger.info(f"Created Portfolio: {portfolio_id} with cash ${starting_cash}")
        return vp

    def get_portfolio(self, portfolio_id: str) -> Optional[VirtualPortfolio]:
        return self.portfolios.get(portfolio_id)

    def register_order(self, order_id: str, portfolio_id: str):
        """Map an outgoing order to a specific portfolio."""
        self.order_map[order_id] = portfolio_id

    def on_execution_fill(self, fill_event: Dict) -> float:
        """
        Route fill event to correct portfolio.
        fill_event must contain 'order_id' or we need a strategy tag.
        """
        order_id = fill_event.get('order_id')
        portfolio_id = self.order_map.get(order_id)
        
        if not portfolio_id:
            # Fallback: check if 'strategy_id' or 'model_id' is in event
            portfolio_id = fill_event.get('strategy_id') or fill_event.get('model_id')
        
        realized_pnl = 0.0
        if portfolio_id and portfolio_id in self.portfolios:
            vp = self.portfolios[portfolio_id]
            realized_pnl = vp.update_from_fill(fill_event)
            logger.info(f"Updated Portfolio {portfolio_id}: Cash=${vp.cash:.2f}")
        else:
            logger.warning(f"Orphan fill received (Order={order_id}). No portfolio found.")
            
        return realized_pnl

    def get_all_portfolios(self, current_prices: Dict[str, float] = None) -> List[Dict]:
        """Return summary of all portfolios for dashboard."""
        if current_prices is None:
            current_prices = {}
            
        results = []
        for p_id, p in self.portfolios.items():
            realized_pnl = sum(t.get('realized_pnl', 0.0) for t in p.history)
            wins = sum(1 for t in p.history if t.get('side') == 'sell' and t.get('realized_pnl', 0.0) > 0)
            total_closed_trades = sum(1 for t in p.history if t.get('side') == 'sell')
            win_rate = (wins / total_closed_trades) if total_closed_trades > 0 else 0.0
            
            equity = p.calculate_total_equity(current_prices)
            pnl = equity - p.initial_cash
            pnl_pct = (pnl / p.initial_cash) * 100 if p.initial_cash > 0 else 0.0
            
            # Basic mapping. E.g. tft_strategy_v1 -> TFT Model
            # This handles fixing 'unknown_model' by defaulting model_name to something readable.
            name_map = {
                "tft_model_01": "TFT Transformer",
                "lstm_model_01": "LSTM DeepNet",
                "lightgbm_01": "LightGBM Quant",
                "sma_cross": "SMA Crossover"
            }
            # Fallback formatting if it doesn't match map
            pretty_name = name_map.get(p_id, p_id.replace("_", " ").title())
            
            results.append({
                "model_id": p_id,
                "model_name": pretty_name,
                "cash": p.cash,
                "equity": equity,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "realized_pnl": realized_pnl,
                "trades": total_closed_trades,
                "wins": wins,
                "win_rate": win_rate,
                "open_positions": len(p.positions)
            })
            
        return results
