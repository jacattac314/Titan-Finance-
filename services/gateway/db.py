import sys
import logging
import os
import asyncio
import asyncpg
import socket
import redis.asyncio as redis
import json

logger = logging.getLogger("TitanDB")

class DatabaseManager:
    def __init__(self):
        self.pg_pool = None
        self.redis = None
        self.quest_host = os.getenv("QUESTDB_HOST", "questdb")
        self.quest_port = int(os.getenv("QUESTDB_PORT", "9009"))  # UDP/TCP Line Protocol
        self.pg_dsn = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}/{os.getenv('POSTGRES_DB')}"
        self.redis_url = f"redis://{os.getenv('REDIS_HOST', 'redis')}:6379"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP for QuestDB

    async def connect(self):
        """Initialize PostgreSQL and Redis connections."""
        try:
            self.pg_pool = await asyncpg.create_pool(self.pg_dsn)
            logger.info("Connected to PostgreSQL.")
            
            self.redis = redis.from_url(self.redis_url)
            await self.redis.ping()
            logger.info("Connected to Redis.")
        except Exception as e:
            logger.error(f"Failed to connect to Infrastructure: {e}")
            raise

    async def close(self):
        """Close all connections."""
        if self.pg_pool:
            await self.pg_pool.close()
            logger.info("PostgreSQL connection pool closed.")
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed.")
        self.sock.close()

    def write_tick(self, symbol: str, price: float, size: int, timestamp: int):
        """
        Send a tick to QuestDB via InfluxDB Line Protocol (UDP for speed).
        Format: market_data,symbol=BTCUSD price=45000.0,size=0.5 1634567890000000000
        """
        try:
            # Line Protocol: measurement,tags fields timestamp(ns)
            line = f"market_data,symbol={symbol} price={price},size={size}i {timestamp}\n"
            self.sock.sendto(line.encode(), (self.quest_host, self.quest_port))
        except Exception as e:
            logger.error(f"Failed to write tick to QuestDB: {e}")

    async def publish_tick(self, symbol: str, price: float, size: int, timestamp: int):
        """Publish tick to Redis channel for real-time consumers."""
        if not self.redis:
            return
            
        try:
            message = json.dumps({
                "symbol": symbol,
                "price": price,
                "size": size,
                "timestamp": timestamp,
                "type": "trade"
            })
            await self.redis.publish("market_data", message)
        except Exception as e:
            logger.error(f"Failed to publish to Redis: {e}")

    async def get_latest_price(self, symbol: str):
        """Fetch latest price from QuestDB (via PG Wire or REST, not implemented in v1 MVP usually just use cache)."""
        # In a real HFT system, we'd query the latest state or keep an in-memory cache.
        pass

db = DatabaseManager()
