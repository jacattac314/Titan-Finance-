import logging
import os
import asyncpg
import redis.asyncio as redis
import json
import pandas as pd

logger = logging.getLogger("TitanSignalDB")

class SignalDB:
    def __init__(self):
        # QuestDB (PG Wire)
        self.quest_user = "admin"
        self.quest_pass = "quest"
        self.quest_host = os.getenv("QUESTDB_HOST", "questdb")
        self.quest_port = int(os.getenv("QUESTDB_PG_PORT", "8812"))
        self.quest_db = "qdb" # Default QuestDB name
        
        # Redis
        self.redis_url = f"redis://{os.getenv('REDIS_HOST', 'redis')}:6379"
        self.redis = None
        self.quest_pool = None

    async def connect(self):
        """Connect to QuestDB and Redis."""
        try:
            # QuestDB via Postgres Wire Protocol
            dsn = f"postgresql://{self.quest_user}:{self.quest_pass}@{self.quest_host}:{self.quest_port}/{self.quest_db}"
            self.quest_pool = await asyncpg.create_pool(dsn)
            logger.info("Connected to QuestDB (PG Wire).")
            
            # Redis
            self.redis = redis.from_url(self.redis_url)
            await self.redis.ping()
            logger.info("Connected to Redis.")
        except Exception as e:
            logger.error(f"Failed to connect to DBs: {e}")
            raise

    async def close(self):
        if self.quest_pool:
            await self.quest_pool.close()
        if self.redis:
            await self.redis.close()

    async def fetch_ohlcv(self, symbol: str, limit: int = 60) -> list:
        """
        Fetch latest OHLCV bars from QuestDB.
        Assumes we have a 'market_data' table or similar (actually gateway writes 'market_data' measurement).
        Gateway writes: symbol, price, size. It's tick data.
        We need to aggregate ticks to bars (e.g., 1-min bars) if we want OHLCV, 
        OR just use raw ticks if the model takes ticks.
        The FeatureEngineer expects: open, high, low, close, volume.
        So we MUST aggregate ticks to bars here using QuestDB's SAMPLE BY.
        """
        if not self.quest_pool:
            return []
            
        try:
            # QuestDB SQL for 1-minute bars
            query = f"""
            SELECT 
                timestamp,
                first(price) as open,
                max(price) as high,
                min(price) as low,
                last(price) as close,
                sum(size) as volume
            FROM market_data
            WHERE symbol = '{symbol}'
            SAMPLE BY 1m ALIGN TO CALENDAR
            ORDER BY timestamp DESC
            LIMIT {limit}
            """
            
            async with self.quest_pool.acquire() as conn:
                rows = await conn.fetch(query)
                
            # Convert to list of dicts and reverse to be chronological (ASC)
            # asyncpg returns Record objects, convert to dict
            data = [dict(row) for row in rows]
            return data[::-1] 
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return []

    async def publish_signal(self, payload: dict):
        """Publish signal to Redis."""
        if not self.redis:
            return
        try:
            await self.redis.publish("trade_signals", json.dumps(payload))
            logger.info(f"Published Signal: {payload['symbol']} {payload['signal']}")
        except Exception as e:
            logger.error(f"Failed to publish signal: {e}")

db = SignalDB()
