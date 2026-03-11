import asyncio
import json
import logging
import os
import random
import sys
import redis.asyncio as redis
from dotenv import load_dotenv

# Strategies
from strategies.sma_crossover import SMACrossover
from strategies.lightgbm_strategy import LightGBMStrategy
from strategies.lstm_strategy import LSTMStrategy
from strategies.tft_strategy import TFTStrategy
from strategies.logistic_regression_strategy import LogisticRegressionStrategy
from strategies.random_forest_strategy import RandomForestStrategy

# Shared schemas and health server
from schemas import MarketDataEvent, TradeSignalEvent, validate_and_log, SCHEMA_VERSION
from health import run_health_server, set_ready, register_liveness_check

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanSignalService")

_MAX_REDIS_RETRIES = 5


async def _connect_redis_with_retry(url: str, logger):
    """Connect to Redis with exponential backoff. Returns client or raises."""
    for attempt in range(1, _MAX_REDIS_RETRIES + 1):
        try:
            client = redis.from_url(url)
            await client.ping()
            logger.info("Connected to Redis (attempt %d).", attempt)
            return client
        except Exception as exc:
            if attempt == _MAX_REDIS_RETRIES:
                logger.critical(
                    "Redis connection failed after %d attempts: %s", attempt, exc
                )
                raise
            wait = (2 ** attempt) + random.random()
            logger.warning(
                "Redis connection attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt, _MAX_REDIS_RETRIES, exc, wait,
            )
            await asyncio.sleep(wait)


async def run_signal_engine(redis_client):
    logger.info("Initializing Signal Engine...")
    
    # 1. Initialize Strategies
    # In a real app, load from DB/Config
    strategies = []
    strategy_configs = [
        (SMACrossover, {"symbol": "SPY", "fast_period": 10, "slow_period": 30, "model_id": "sma_spy"}),
        (LightGBMStrategy, {"symbol": "SPY", "model_id": "lgb_spy_v1", "confidence_threshold": 0.6}),
        (LSTMStrategy, {"symbol": "SPY", "model_id": "lstm_spy_v1", "lookback": 60}),
        (TFTStrategy, {"symbol": "SPY", "model_id": "tft_spy_v1", "lookback": 60}),
        (LogisticRegressionStrategy, {"symbol": "SPY", "model_id": "logreg_spy_v1", "confidence_threshold": 0.58}),
        (RandomForestStrategy, {"symbol": "SPY", "model_id": "rf_spy_v1", "confidence_threshold": 0.62}),
    ]
    for cls, cfg in strategy_configs:
        try:
            strategies.append(cls(cfg))
        except Exception as exc:
            logger.error("Failed to initialise strategy %s: %s. Skipping.", cls.__name__, exc)

    if not strategies:
        logger.critical("No strategies initialised — signal service cannot run.")
        return

    logger.info("Loaded %d/%d strategies.", len(strategies), len(strategy_configs))

    # 2. Subscribe to Market Data
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("market_data")
    logger.info("Listening for market data...")

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
    try:
        redis_client = await _connect_redis_with_retry(f"redis://{redis_host}:6379", logger)
    except Exception:
        return

    async def _check_redis() -> tuple[bool, str | None]:
        try:
            await redis_client.ping()
            return True, None
        except Exception as exc:
            return False, str(exc)

    register_liveness_check(_check_redis)

    await asyncio.gather(
        run_health_server(service="titan-signal"),
        run_signal_engine(redis_client),
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SignalEngine stopped.")
