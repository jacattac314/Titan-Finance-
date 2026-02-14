import asyncio
import os
import logging
import sys
from dotenv import load_dotenv

# Load environment variables from .env file (for local dev)
load_dotenv()

from db import db
from alpaca import AlpacaAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("TitanGateway")

# Simple in-memory list of symbols to track for v1
WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "TSLA", "NVDA", "AMD", "AMZN"]

async def handle_tick(tick_data):
    """Callback for when a new tick is received."""
    # 1. Log to console (debug) or Redis (production)
    # logger.debug(f"Tick: {tick_data['symbol']} @ {tick_data['price']}")
    
    # 2. Write to QuestDB (Fast path)
    db.write_tick(
        symbol=tick_data['symbol'],
        price=tick_data['price'],
        size=tick_data['size'],
        timestamp=tick_data['timestamp'] # Nanoseconds
    )

    # 3. Publish to Redis (Real-time path)
    await db.publish_tick(
        symbol=tick_data['symbol'],
        price=tick_data['price'],
        size=tick_data['size'],
        timestamp=tick_data['timestamp']
    )

async def main():
    logger.info("Starting TitanFlow MarketDataGateway...")
    
    # 1. Connect to Infrastructure
    try:
        await db.connect() # Postgres
        # QuestDB uses UDP, no explicit connect needed for ingest
    except Exception as e:
        logger.error(f"Infrastructure connection failed: {e}")
        return

    # 2. Initialize Adapter
    adapter = AlpacaAdapter(WATCHLIST, handle_tick)
    
    # 3. specific Run Loop
    try:
        await adapter.run()
    except Exception as e:
        logger.error(f"Adapter runtime error: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gateway stopped by user.")
