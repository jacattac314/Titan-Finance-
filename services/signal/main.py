import asyncio
import json
import logging
import os
import sys
import redis.asyncio as redis
from dotenv import load_dotenv

from db import db

# Strategies
from strategies.sma_crossover import SMACrossover
from strategies.lightgbm_strategy import LightGBMStrategy
from strategies.lstm_strategy import LSTMStrategy
from strategies.tft_strategy import TFTStrategy

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanSignalService")

async def run_signal_engine(redis_client):
    logger.info("Initializing Signal Engine...")
    
    # 1. Initialize Strategies
    # In a real app, load from DB/Config
    strategies = [
        SMACrossover({"symbol": "SPY", "fast_period": 10, "slow_period": 30, "model_id": "sma_spy"}),
        LightGBMStrategy({"symbol": "SPY", "model_id": "lgb_spy_v1", "confidence_threshold": 0.6}),
        LSTMStrategy({"symbol": "SPY", "model_id": "lstm_spy_v1", "lookback": 60}),
        TFTStrategy({"symbol": "SPY", "model_id": "tft_spy_v1", "lookback": 60})
    ]
    
    # 2. Subscribe to Market Data
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("market_data")
    logger.info(f"Loaded {len(strategies)} strategies. Listening for market data...")

    async for message in pubsub.listen():
        try:
            if message.get("type") != "message":
                continue

            data = json.loads(message["data"])
            
            # 3. Process Tick
            if data.get("type") == "trade":
                for strategy in strategies:
                    if strategy.symbol == data.get("symbol"):
                        signal = await strategy.on_tick(data)
                        
                        if signal:
                           # 4.Publish Signal
                           logger.info(f"Signal Generated: {signal}")
                           await redis_client.publish("trade_signals", json.dumps(signal))

        except Exception as e:
            logger.error(f"Error processing tick: {e}")

async def main():
    logger.info("Starting TitanFlow SignalEngine...")
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_client = redis.from_url(f"redis://{redis_host}:6379")

    try:
        await redis_client.ping()
        logger.info("Connected to Redis.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return

    try:
        await db.connect()
    except Exception as e:
        logger.warning(f"Signal DB unavailable (non-fatal, continuing without historical bars): {e}")

    try:
        await run_signal_engine(redis_client)
    finally:
        await db.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SignalEngine stopped.")
