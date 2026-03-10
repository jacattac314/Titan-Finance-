from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def _to_epoch_ms(ts) -> int:
    """Parse a timestamp to epoch-milliseconds.

    Accepts int/float (epoch-ms or epoch-s) and ISO 8601 strings.
    """
    if isinstance(ts, (int, float)):
        v = int(ts)
        return v if v > 1_000_000_000_000 else v * 1000  # seconds → ms
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(datetime.now(timezone.utc).timestamp() * 1000)


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
