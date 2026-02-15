import asyncio
import logging
import random
import math
from datetime import datetime, timedelta
from typing import List, Callable, Dict, Any
import pandas as pd

from .base import DataProvider

logger = logging.getLogger("TitanSyntheticProvider")

class SyntheticDataProvider(DataProvider):
    """
    Generates synthetic market data using Geometric Brownian Motion (GBM).
    Useful for testing the pipeline without external API dependencies.
    """
    
    def __init__(self, api_keys: Dict[str, str] = None):
        super().__init__(api_keys or {})
        # Initial prices for our fake assets
        self.prices = {
            "SPY": 450.0,
            "QQQ": 380.0,
            "AAPL": 175.0,
            "MSFT": 350.0,
            "TSLA": 240.0,
            "NVDA": 480.0,
            "AMD": 110.0,
            "AMZN": 145.0
        }
        self.volatility = 0.0002 # Per-tick volatility
        self.dt = 1/252/390/60 # Approx 1 second in trading years (very rough)
        self.is_running = False

    async def subscribe(self, symbols: List[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        """Start generating synthetic trades."""
        self.is_running = True
        logger.info(f"Starting Synthetic Data Stream for: {symbols}")
        
        while self.is_running:
            for symbol in symbols:
                if symbol not in self.prices:
                    self.prices[symbol] = 100.0 # Default start

                # Geometric Brownian Motion Step
                # dS = S * (mu*dt + sigma*dW)
                # Simplified: S_new = S_old * exp(drift + diffusion)
                shock = random.gauss(0, self.volatility)
                self.prices[symbol] *= math.exp(shock)
                
                # Create Trade Object
                price = round(self.prices[symbol], 2)
                size = random.randint(1, 100)
                
                trade = {
                    "type": "trade",
                    "symbol": symbol,
                    "price": price,
                    "size": size,
                    "timestamp": int(datetime.utcnow().timestamp() * 1e9),
                    "provider": "synthetic"
                }
                
                await callback(trade)
            
            # Throttle to mimic realistic tick rate (e.g. 10 updates per second total loop)
            await asyncio.sleep(0.1)

    def get_historical_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> pd.DataFrame:
        """Generate fake historical data."""
        # Simple generation for now, just to satisfy interface
        dates = pd.date_range(start=start, end=end, freq='D' if timeframe == '1Day' else '1min')
        df = pd.DataFrame(index=dates)
        
        # Random walk
        price = 100.0
        prices = []
        for _ in range(len(dates)):
            change = random.gauss(0, 0.01)
            price *= (1 + change)
            prices.append(price)
            
        df['close'] = prices
        df['open'] = df['close'].shift(1).fillna(prices[0])
        df['high'] = df[['open', 'close']].max(axis=1) * 1.005
        df['low'] = df[['open', 'close']].min(axis=1) * 0.995
        df['volume'] = [random.randint(1000, 50000) for _ in range(len(dates))]
        
        return df

    def get_latest_price(self, symbol: str) -> float:
        return self.prices.get(symbol, 100.0)
