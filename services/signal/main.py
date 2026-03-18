import asyncio
import json
import logging
import os
import sys
import redis.asyncio as redis
from dotenv import load_dotenv

# Contender registry (loads strategies from contenders.yaml / CONTENDERS_CONFIG)
from contender_registry import load_contenders

# Shared schemas and health server
from schemas import MarketDataEvent, TradeSignalEvent, validate_and_log, SCHEMA_VERSION
from health import run_health_server, set_ready

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanSignalService")

async def run_signal_engine(redis_client):
    logger.info("Initializing Signal Engine...")

    # 1. Load strategies from contenders.yaml (or CONTENDERS_CONFIG env var)
    strategies = load_contenders()
    
    # 2. Subscribe to Market Data
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("market_data")
    logger.info(f"Loaded {len(strategies)} strategies. Listening for market data...")

    set_ready(True)

    async for message in pubsub.listen():
        try:
            if message.get("type") != "message":
                continue

            raw = json.loads(message["data"])

            # Validate incoming market data event
            market_event = validate_and_log(MarketDataEvent, raw, context="signal:consume:market_data")
            if market_event is None:
                continue

            # 3. Process Tick
            if market_event.type == "trade":
                for strategy in strategies:
                    if strategy.symbol == market_event.symbol:
                        signal = await strategy.on_tick(raw)

                        if signal:
                            # Stamp schema_version before publishing
                            signal.setdefault("schema_version", SCHEMA_VERSION)

                            # Validate outgoing signal before publishing
                            validated = validate_and_log(
                                TradeSignalEvent, signal, context="signal:publish:trade_signals"
                            )
                            if validated is None:
                                logger.warning("Dropping malformed signal from %s", strategy)
                                continue

                            logger.info(f"Signal Generated: {signal}")
                            await redis_client.publish(
                                "trade_signals", json.dumps(validated.to_dict())
                            )

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

    await asyncio.gather(
        run_health_server(service="titan-signal"),
        run_signal_engine(redis_client),
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SignalEngine stopped.")
