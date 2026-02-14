import os
import logging
import json
import asyncio
from websockets.client import connect  # Needs `websockets` package
from .adapter import MarketDataAdapter

logger = logging.getLogger("TitanAlpaca")

class AlpacaAdapter(MarketDataAdapter):
    def __init__(self, symbols, on_tick):
        super().__init__(symbols, on_tick)
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.base_url = "wss://stream.data.alpaca.markets/v2/iex" # Use IEX for free/paper data
        self.ws = None

    async def connect(self):
        logger.info(f"Connecting to Alpaca Stream: {self.base_url}")
        self.ws = await connect(self.base_url)
        
        # Authenticate
        auth_payload = {
            "action": "auth",
            "key": self.api_key,
            "secret": self.secret_key
        }
        await self.ws.send(json.dumps(auth_payload))
        response = await self.ws.recv()
        logger.info(f"Auth Response: {response}")

    async def subscribe(self):
        if not self.ws:
            raise RuntimeError("WebSocket not connected")
            
        sub_payload = {
            "action": "subscribe",
            "trades": self.symbols,
            # "quotes": self.symbols, # Uncomment for quotes, v1 uses trades only for simplicity
            # "bars": ["*"] 
        }
        await self.ws.send(json.dumps(sub_payload))
        logger.info(f"Subscribed to: {self.symbols}")

    async def run(self):
        if not self.ws:
            await self.connect()
            await self.subscribe()
            
        async for message in self.ws:
            data = json.loads(message)
            for item in data:
                if item.get("T") == "t": # Trade message
                    # Normalize to TitanFlow standard format
                    normalized = {
                        "type": "trade",
                        "symbol": item["S"],
                        "price": float(item["p"]),
                        "size": int(item["s"]),
                        "timestamp": int(item["t"].replace("-", "").replace(":", "").replace("T", "").replace("Z","")) * 1000000 # Rough parse to ns
                    }
                    await self.on_tick(normalized)
