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
from strategies.logistic_regression_strategy import LogisticRegressionStrategy
from strategies.random_forest_strategy import RandomForestStrategy

# PyTorch-dependent strategies — optional, skipped if torch is not installed
try:
    from strategies.lstm_strategy import LSTMStrategy
    from strategies.tft_strategy import TFTStrategy
    _TORCH_AVAILABLE = True
except ImportError:
    LSTMStrategy = None  # type: ignore[assignment,misc]
    TFTStrategy = None   # type: ignore[assignment,misc]
    _TORCH_AVAILABLE = False

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
    
    # 1. Initialize Strategies
    # In a real app, load from DB/Config
    strategies = [
        SMACrossover({"symbol": "SPY", "fast_period": 10, "slow_period": 30, "model_id": "sma_spy"}),
        LightGBMStrategy({"symbol": "SPY", "model_id": "lgb_spy_v1", "confidence_threshold": 0.6}),
        LogisticRegressionStrategy({"symbol": "SPY", "model_id": "logreg_spy_v1", "confidence_threshold": 0.58}),
        RandomForestStrategy({"symbol": "SPY", "model_id": "rf_spy_v1", "confidence_threshold": 0.62}),
    ]
    if _TORCH_AVAILABLE:
        strategies += [
            LSTMStrategy({"symbol": "SPY", "model_id": "lstm_spy_v1", "lookback": 60}),
            TFTStrategy({"symbol": "SPY", "model_id": "tft_spy_v1", "lookback": 60}),
        ]
    else:
        logger.warning("torch not installed — LSTM and TFT strategies disabled.")
    
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
