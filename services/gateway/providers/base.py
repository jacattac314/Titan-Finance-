from abc import ABC, abstractmethod
import pandas as pd
from datetime import datetime
from typing import List, Callable, Dict, Any

class DataProvider(ABC):
    """
    Abstract Base Class for Market Data Providers.
    Enforces a standard interface for real-time streaming and historical data fetching.
    """
    
    def __init__(self, api_keys: Dict[str, str]):
        self.api_keys = api_keys

    @abstractmethod
    async def subscribe(self, symbols: List[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to real-time updates for the given symbols.
        
        Args:
            symbols: List of ticker symbols (e.g., ["SPY", "AAPL"]).
            callback: Async function to call with normalized tick data.
        """
        pass
        
    @abstractmethod
    def get_historical_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> pd.DataFrame:
        """
        Fetch historical bar data.
        
        Args:
            symbol: Ticker symbol.
            start: Start datetime.
            end: End datetime.
            timeframe: "1Min", "1Hour", "1Day".
            
        Returns:
            pd.DataFrame: OHLCV data with DatetimeIndex.
        """
        pass
        
    @abstractmethod
    def get_latest_price(self, symbol: str) -> float:
        """
        Get the latest snapshot price for a symbol.
        """
        pass
