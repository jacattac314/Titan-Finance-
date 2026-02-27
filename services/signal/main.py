import asyncio
import json
import logging
import os
import sys
import redis.asyncio as redis
from dotenv import load_dotenv

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

    # 1. Initialize Strategies — read symbols from env (comma-separated, default SPY)
    raw_symbols = os.getenv("TRADING_SYMBOLS", "SPY").upper()
    symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]
    logger.info(f"Trading symbols: {symbols}")

    strategies = []
    for sym in symbols:
        strategies.extend([
            SMACrossover({"symbol": sym, "fast_period": 10, "slow_period": 30, "model_id": f"sma_{sym.lower()}"}),
            LightGBMStrategy({"symbol": sym, "model_id": f"lgb_{sym.lower()}_v1", "confidence_threshold": 0.6}),
            LSTMStrategy({"symbol": sym, "model_id": f"lstm_{sym.lower()}_v1", "lookback": 60}),
            TFTStrategy({"symbol": sym, "model_id": f"tft_{sym.lower()}_v1", "lookback": 60}),
        ])

    # 2. Subscribe to Market Data
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("market_data")
    logger.info(f"Loaded {len(strategies)} strategies across {len(symbols)} symbol(s). Listening for market data...")

    _HEARTBEAT_INTERVAL = 30  # seconds
    last_heartbeat = asyncio.get_running_loop().time()

    while True:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                await redis_client.ping()
                last_heartbeat = now

            if message is None:
                continue

            data = json.loads(message["data"])

            # 3. Process Tick
            if data.get("type") == "trade":
                for strategy in strategies:
                    if strategy.symbol == data.get("symbol"):
                        signal = await strategy.on_tick(data)

                        if signal:
                            # 4. Publish Signal
                            logger.info(f"Signal Generated: {signal}")
                            await redis_client.publish("trade_signals", json.dumps(signal))

        except (redis.ConnectionError, redis.TimeoutError, OSError) as exc:
            logger.error(f"Redis connection lost in signal engine: {exc}. Reconnecting in 5s...")
            await asyncio.sleep(5)
            try:
                pubsub = redis_client.pubsub()
                await pubsub.subscribe("market_data")
                last_heartbeat = asyncio.get_running_loop().time()
                logger.info("Reconnected to Redis.")
            except Exception as reconnect_exc:
                logger.error(f"Reconnect failed: {reconnect_exc}")
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

    await run_signal_engine(redis_client)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SignalEngine stopped.")
