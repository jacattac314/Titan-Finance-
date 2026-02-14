from abc import ABC, abstractmethod
from typing import Callable, List, Awaitable

class MarketDataAdapter(ABC):
    """
    Abstract Base Class for Data Providers.
    Ensures that switching from Alpaca to Polygon or IBKR is transparent to the core logic.
    """
    
    def __init__(self, symbols: List[str], on_tick: Callable[[dict], Awaitable[None]]):
        self.symbols = symbols
        self.on_tick = on_tick # Callback function (async)

    @abstractmethod
    async def connect(self):
        """Establish connection to the provider's WebSocket."""
        pass

    @abstractmethod
    async def subscribe(self):
        """Subscribe to the specified symbols."""
        pass

    @abstractmethod
    async def run(self):
        """Main loop to process incoming messages."""
        pass
