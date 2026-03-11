"""
TitanFlow RiskGuardian — asynchronous risk monitoring service.

Subscribes to the ``trade_signals`` Redis channel and applies the
RiskEngine governance layer before forwarding approved signals to
``execution_requests``.

Enterprise controls wired in:
    • Kill switch      — halts trading + triggers liquidation command.
    • Manual approval  — forwarded to connector via Redis command channel.
    • Model rollback   — checked after every N trades via check_model_performance().
"""

import asyncio
import json
import logging
import os
import random
import sys

import redis.asyncio as redis
from dotenv import load_dotenv

from risk_engine import RiskEngine
from schemas import (
    TradeSignalEvent,
    ExecutionRequestEvent,
    ExecutionFilledEvent,
    validate_and_log,
    SCHEMA_VERSION,
)
from health import run_health_server, set_ready, register_liveness_check

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TitanRiskGuardian")

# How often to evaluate rolling model metrics (every N signals processed)
_PERFORMANCE_CHECK_INTERVAL = int(os.getenv("RISK_PERF_CHECK_INTERVAL", "10"))


def _load_and_validate_config() -> dict:
    """Load risk configuration from environment variables and validate ranges."""
    try:
        config = {
            "MAX_DAILY_LOSS_PCT": float(os.getenv("RISK_MAX_DAILY_LOSS", "0.03")),
            "RISK_PER_TRADE_PCT": float(os.getenv("RISK_PER_TRADE", "0.01")),
            "MAX_CONSECUTIVE_LOSSES": int(os.getenv("CIRCUIT_BREAKER_CONSECUTIVE_LOSSES", "5")),
            "ROLLBACK_MIN_SHARPE": float(os.getenv("ROLLBACK_MIN_SHARPE", "0.5")),
            "ROLLBACK_MIN_ACCURACY": float(os.getenv("ROLLBACK_MIN_ACCURACY", "0.50")),
        }
    except ValueError as exc:
        logger.critical("Invalid risk configuration value: %s", exc)
        sys.exit(1)

    errors = []
    if not (0.001 <= config["MAX_DAILY_LOSS_PCT"] <= 1.0):
        errors.append(
            f"RISK_MAX_DAILY_LOSS={config['MAX_DAILY_LOSS_PCT']} must be in [0.001, 1.0]"
        )
    if not (0.0001 <= config["RISK_PER_TRADE_PCT"] <= 0.5):
        errors.append(
            f"RISK_PER_TRADE={config['RISK_PER_TRADE_PCT']} must be in [0.0001, 0.5]"
        )
    if config["MAX_CONSECUTIVE_LOSSES"] < 1:
        errors.append(
            f"CIRCUIT_BREAKER_CONSECUTIVE_LOSSES={config['MAX_CONSECUTIVE_LOSSES']} must be >= 1"
        )
    if not (0.0 <= config["ROLLBACK_MIN_SHARPE"] <= 10.0):
        errors.append(
            f"ROLLBACK_MIN_SHARPE={config['ROLLBACK_MIN_SHARPE']} must be in [0.0, 10.0]"
        )
    if not (0.0 <= config["ROLLBACK_MIN_ACCURACY"] <= 1.0):
        errors.append(
            f"ROLLBACK_MIN_ACCURACY={config['ROLLBACK_MIN_ACCURACY']} must be in [0.0, 1.0]"
        )

    if errors:
        for err in errors:
            logger.critical("Config validation error: %s", err)
        sys.exit(1)

    return config


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


async def main():
    logger.info("Starting TitanFlow RiskGuardian...")

    config = _load_and_validate_config()

    engine = RiskEngine(config)
    logger.info(
        f"RiskEngine ready | max_drawdown={config['MAX_DAILY_LOSS_PCT']:.1%} "
        f"| max_consec_losses={config['MAX_CONSECUTIVE_LOSSES']} "
        f"| rollback_sharpe={config['ROLLBACK_MIN_SHARPE']}"
    )

    # --- Connect to Redis ---
    redis_host = os.getenv("REDIS_HOST", "redis")
    try:
        r = await _connect_redis_with_retry(f"redis://{redis_host}:6379", logger)
    except Exception:
        return
    pubsub = r.pubsub()
    await pubsub.subscribe("trade_signals", "execution_filled")
    logger.info("Subscribed to [trade_signals, execution_filled].")

    async def _check_redis() -> tuple[bool, str | None]:
        try:
            await r.ping()
            return True, None
        except Exception as exc:
            return False, str(exc)

    register_liveness_check(_check_redis)

    signals_processed = 0

    set_ready(True)
    logger.info("RiskGuardian listening for events...")

    async for message in pubsub.listen():
        try:
            if message["type"] != "message":
                continue

            channel = message.get("channel", b"")
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")

            data = json.loads(message["data"])

            # ----------------------------------------------------------------
            # execution_filled: record trade result for model-performance tracking
            # ----------------------------------------------------------------
            if channel == "execution_filled":
                fill = validate_and_log(
                    ExecutionFilledEvent, data, context="risk:consume:execution_filled"
                )
                if fill is None:
                    continue

                if fill.price > 0:
                    raw_return = -fill.slippage / fill.price  # negative slippage = cost
                    correct_direction = (
                        raw_return >= 0 if fill.side == "BUY" else raw_return <= 0
                    )
                    engine.record_trade_result(raw_return)
                    engine.record_prediction(correct_direction, raw_return)
                continue

            # ----------------------------------------------------------------
            # trade_signals: apply risk governance before forwarding
            # ----------------------------------------------------------------
            signal_event = validate_and_log(
                TradeSignalEvent, data, context="risk:consume:trade_signals"
            )
            if signal_event is None:
                continue

            logger.info(f"Received signal: {data}")

            # 1. Validate (kill switch + manual approval mode)
            if not engine.validate_signal(data):
                if engine.is_kill_switch_active:
                    # Broadcast liquidation command so execution service reacts
                    await r.publish("risk_commands", json.dumps({
                        "command": "LIQUIDATE_ALL",
                        "reason": "kill_switch_active",
                    }))
                continue

            # 2. Evaluate kill switch conditions
            if engine.check_kill_switch():
                logger.warning("Kill switch triggered — publishing LIQUIDATE_ALL command.")
                await r.publish("risk_commands", json.dumps({
                    "command": "LIQUIDATE_ALL",
                    "reason": "drawdown_or_consecutive_loss_limit_breached",
                }))
                continue

            # 3. Calculate position size (Fixed Fractional)
            price = signal_event.price
            if price <= 0:
                logger.error(f"Signal missing valid price: {data}")
                continue

            stop_loss = price * (0.98 if signal_event.signal == "BUY" else 1.02)
            units = engine.calculate_position_size(price, stop_loss, symbol=signal_event.symbol)

            if units <= 0:
                logger.info(f"Position size=0 for {signal_event.symbol} — skipping.")
                continue

            # 4. Build and validate the execution request before publishing
            execution_payload = ExecutionRequestEvent(
                model_id=signal_event.model_id,
                symbol=signal_event.symbol,
                qty=units,
                side="buy" if signal_event.signal == "BUY" else "sell",
                type="market",
                confidence=signal_event.confidence,
                explanation=signal_event.explanation,
                timestamp=signal_event.timestamp,
                schema_version=SCHEMA_VERSION,
            )
            await r.publish("execution_requests", json.dumps(execution_payload.to_dict()))
            logger.info(
                f"Approved → {execution_payload.side.upper()} "
                f"{units} {execution_payload.symbol}"
            )

            # 5. Periodic model performance check → rollback if needed
            signals_processed += 1
            if signals_processed % _PERFORMANCE_CHECK_INTERVAL == 0:
                rolled_back = engine.check_model_performance()
                if rolled_back:
                    sharpe = engine.get_rolling_sharpe()
                    accuracy = engine.get_rolling_accuracy()
                    await r.publish("risk_commands", json.dumps({
                        "command": "ACTIVATE_MANUAL_APPROVAL",
                        "reason": "model_performance_below_threshold",
                        "rolling_sharpe": sharpe,
                        "rolling_accuracy": accuracy,
                    }))
                    logger.warning(
                        f"Model rollback published | sharpe={sharpe} accuracy={accuracy}"
                    )

        except Exception as exc:
            logger.error(f"Error processing message: {exc}")


async def _run():
    health = asyncio.create_task(run_health_server(service="titan-risk"))
    await main()
    health.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("RiskGuardian stopped.")
