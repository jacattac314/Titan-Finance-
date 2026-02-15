import asyncio
import json
import logging
from typing import List, Callable, Dict, Any
from datetime import datetime
import pandas as pd
import websockets

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from .base import DataProvider

logger = logging.getLogger("TitanAlpacaProvider")

class AlpacaDataProvider(DataProvider):
    """
    Implementation of DataProvider using raw Websockets for streaming
    and Alpaca-py SDK for historical data.
    """
    
    def __init__(self, api_keys: Dict[str, str]):
        super().__init__(api_keys)
        self.api_key = api_keys.get("ALPACA_API_KEY")
        self.secret_key = api_keys.get("ALPACA_SECRET_KEY")
        self.base_url = "wss://stream.data.alpaca.markets/v2/iex" # Free/Paper data
        
        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca API keys (ALPACA_API_KEY, ALPACA_SECRET_KEY) are required.")

        # Initialize Historical Client
        self.history_client = StockHistoricalDataClient(self.api_key, self.secret_key)
        self.callback = None
        self.ws = None

    async def _connect_and_auth(self):
        """Connect and Authenticate."""
        logger.info(f"Connecting to {self.base_url}...")
        self.ws = await websockets.connect(self.base_url)
        
        # Auth
        auth_payload = {
            "action": "auth",
            "key": self.api_key,
            "secret": self.secret_key
        }
        await self.ws.send(json.dumps(auth_payload))
        response = await self.ws.recv()
        logger.info(f"Auth Response: {response}")

    async def subscribe(self, symbols: List[str], callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to real-time trade updates."""
        self.callback = callback
        
        while True:
            try:
                await self._connect_and_auth()
                
                # Subscribe
                sub_payload = {
                    "action": "subscribe",
                    "trades": symbols
                }
                await self.ws.send(json.dumps(sub_payload))
                logger.info(f"Subscribed to trades for: {symbols}")
                
                # Listen
                async for message in self.ws:
                    data = json.loads(message)
                    for item in data:
                        if item.get("T") == "t": # Trade
                            # Normalize
                            normalized = {
                                "type": "trade",
                                "symbol": item.get("S"),
                                "price": float(item.get("p", 0)),
                                "size": int(item.get("s", 0)),
                                "timestamp": int(item.get("t", "0").replace("-", "").replace(":", "").replace("T", "").replace("Z","")) * 1e9 if "t" in item else 0, # Crude parse, mostly for v1
                                "provider": "alpaca"
                            }
                            # Better timestamp parsing if possible:
                            # from dateutil import parser
                            # ts = parser.parse(item["t"]).timestamp() * 1e9
                            
                            await callback(normalized)
                        elif item.get("T") == "error":
                            logger.error(f"Stream error: {item}")
                            
            except Exception as e:
                logger.error(f"Stream connection lost: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def get_historical_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> pd.DataFrame:
        """Fetch historical bars."""
        # Method remains same
        tf_map = {
            "1Min": TimeFrame.Minute,
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day
        }
        
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf_map.get(timeframe, TimeFrame.Minute),
            start=start,
            end=end
        )
        
        bars = self.history_client.get_stock_bars(request)
        return bars.df

    def get_latest_price(self, symbol: str) -> float:
        snapshot = self.history_client.get_stock_snapshot(symbol)
        if snapshot and symbol in snapshot:
             return snapshot[symbol].latest_trade.price
        return 0.0
