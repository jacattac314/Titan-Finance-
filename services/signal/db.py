import logging
import os
from urllib.parse import quote_plus
import asyncpg
import asyncpg.exceptions
import redis.asyncio as redis
import json
import pandas as pd

logger = logging.getLogger("TitanSignalDB")

class SignalDB:
    def __init__(self):
        # QuestDB (PG Wire) — credentials must be supplied via environment variables.
        # Falling back to the well-known QuestDB OSS defaults; a warning is emitted
        # so operators can identify insecure configurations at startup.
        self.quest_user = os.getenv("QUESTDB_USER", "admin")
        self.quest_pass = os.getenv("QUESTDB_PASS", "quest")
        self.quest_host = os.getenv("QUESTDB_HOST", "questdb")
        self.quest_port = int(os.getenv("QUESTDB_PG_PORT", "8812"))
        self.quest_db = "qdb"  # Default QuestDB database name

        if self.quest_user == "admin" and self.quest_pass == "quest":
            logger.warning(
                "QuestDB is using default credentials (admin/quest). "
                "Set QUESTDB_USER and QUESTDB_PASS environment variables for production."
            )

        # Redis
        self.redis_url = f"redis://{os.getenv('REDIS_HOST', 'redis')}:6379"
        self.redis = None
        self.quest_pool = None

    async def connect(self):
        """Connect to QuestDB and Redis."""
        try:
            # Build DSN with URL-encoded password to handle special characters safely.
            # The password is never logged; only the host/port are emitted.
            encoded_pass = quote_plus(self.quest_pass)
            dsn = (
                f"postgresql://{self.quest_user}:{encoded_pass}"
                f"@{self.quest_host}:{self.quest_port}/{self.quest_db}"
            )
            self.quest_pool = await asyncpg.create_pool(dsn)
            logger.info(
                "Connected to QuestDB (PG Wire) at %s:%s.",
                self.quest_host, self.quest_port,
            )

            # Redis
            self.redis = redis.from_url(self.redis_url)
            await self.redis.ping()
            logger.info("Connected to Redis.")
        except (asyncpg.PostgresError, OSError, asyncpg.exceptions.ConnectionDoesNotExistError) as e:
            logger.error("Failed to connect to QuestDB: %s", e)
            raise
        except redis.RedisError as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise

    async def close(self):
        if self.quest_pool:
            await self.quest_pool.close()
        if self.redis:
            await self.redis.close()

    async def fetch_ohlcv(self, symbol: str, limit: int = 60) -> list:
        """
        Fetch latest OHLCV bars from QuestDB.

        Uses a parameterised query ($1) to prevent SQL injection on the symbol
        parameter.  The ``limit`` value is a validated integer so it is safe to
        interpolate directly into the query string.
        """
        if not self.quest_pool:
            return []

        # Clamp limit to a safe, positive integer to avoid edge-case injection
        # through the LIMIT clause (even though it is an internal parameter).
        safe_limit = max(1, min(int(limit), 1000))

        query = f"""
        SELECT
            timestamp,
            first(price) as open,
            max(price)   as high,
            min(price)   as low,
            last(price)  as close,
            sum(size)    as volume
        FROM market_data
        WHERE symbol = $1
        SAMPLE BY 1m ALIGN TO CALENDAR
        ORDER BY timestamp DESC
        LIMIT {safe_limit}
        """

        try:
            async with self.quest_pool.acquire() as conn:
                rows = await conn.fetch(query, symbol)

            # Convert to list of dicts and reverse to chronological order (ASC)
            data = [dict(row) for row in rows]
            return data[::-1]

        except asyncpg.PostgresError as e:
            logger.error("DB error fetching OHLCV for %s: %s", symbol, e)
            return []

    async def publish_signal(self, payload: dict):
        """Publish signal to Redis."""
        if not self.redis:
            return
        try:
            await self.redis.publish("trade_signals", json.dumps(payload))
            logger.info("Published Signal: %s %s", payload['symbol'], payload['signal'])
        except redis.RedisError as e:
            logger.error("Failed to publish signal: %s", e)

db = SignalDB()
