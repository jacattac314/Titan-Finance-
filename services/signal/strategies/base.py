from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class Strategy(ABC):
    """
    Abstract Base Class for all quantitative strategies.
    Enforces a standard interface for signal generation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.symbol = config.get("symbol", "SPY")
        self.model_id = config.get("model_id", "unknown_strategy")

    @abstractmethod
    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a new tick/trade event.
        Returns a Signal dictionary or None.
        Signal format: { "model_id": "...", "symbol": "...", "signal": "BUY", "confidence": 0.8 }
        """
        pass
        
    @abstractmethod
    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a new OHLCV bar."""
        pass
