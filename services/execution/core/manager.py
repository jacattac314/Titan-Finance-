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

    def on_execution_fill(self, fill_event: Dict):
        """
        Route fill event to correct portfolio.
        fill_event must contain 'order_id' or we need a strategy tag.
        """
        order_id = fill_event.get('order_id')
        portfolio_id = self.order_map.get(order_id)
        
        if not portfolio_id:
            # Fallback: check if 'strategy_id' is in event
            portfolio_id = fill_event.get('strategy_id')
        
        if portfolio_id and portfolio_id in self.portfolios:
            vp = self.portfolios[portfolio_id]
            vp.update_from_fill(fill_event)
            logger.info(f"Updated Portfolio {portfolio_id}: Cash=${vp.cash:.2f}")
        else:
            logger.warning(f"Orphan fill received (Order={order_id}). No portfolio found.")

    def get_all_portfolios(self) -> List[Dict]:
        """Return summary of all portfolios for dashboard."""
        return [
            {
                "id": p_id,
                "cash": p.cash,
                "positions_count": len(p.positions),
                "equity": p.calculate_total_equity({}) # TODO: Pass real prices
            }
            for p_id, p in self.portfolios.items()
        ]
