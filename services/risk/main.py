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
import sys

import redis.asyncio as redis
from dotenv import load_dotenv

from risk_engine import RiskEngine

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TitanRiskGuardian")

# How often to evaluate rolling model metrics (every N signals processed)
_PERFORMANCE_CHECK_INTERVAL = int(os.getenv("RISK_PERF_CHECK_INTERVAL", "10"))


async def main():
    logger.info("Starting TitanFlow RiskGuardian...")

    config = {
        "MAX_DAILY_LOSS_PCT": float(os.getenv("RISK_MAX_DAILY_LOSS", 0.03)),
        "RISK_PER_TRADE_PCT": float(os.getenv("RISK_PER_TRADE", 0.01)),
        "MAX_CONSECUTIVE_LOSSES": int(os.getenv("CIRCUIT_BREAKER_CONSECUTIVE_LOSSES", 5)),
        "ROLLBACK_MIN_SHARPE": float(os.getenv("ROLLBACK_MIN_SHARPE", 0.5)),
        "ROLLBACK_MIN_ACCURACY": float(os.getenv("ROLLBACK_MIN_ACCURACY", 0.50)),
    }

    engine = RiskEngine(config)
    logger.info(
        f"RiskEngine ready | max_drawdown={config['MAX_DAILY_LOSS_PCT']:.1%} "
        f"| max_consec_losses={config['MAX_CONSECUTIVE_LOSSES']} "
        f"| rollback_sharpe={config['ROLLBACK_MIN_SHARPE']}"
    )

    # --- Connect to Redis ---
    redis_host = os.getenv("REDIS_HOST", "redis")
    try:
        r = redis.from_url(f"redis://{redis_host}:6379")
        await r.ping()
        pubsub = r.pubsub()
        await pubsub.subscribe("trade_signals", "execution_filled")
        logger.info("Connected to Redis. Subscribed to [trade_signals, execution_filled].")
    except Exception as exc:
        logger.error(f"Failed to connect to Redis: {exc}")
        return

    signals_processed = 0

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
                # Infer a simple trade return from slippage/price for rolling Sharpe
                price = float(data.get("price", 0) or 0)
                slippage = float(data.get("slippage", 0) or 0)
                side = data.get("side", "BUY").upper()

                if price > 0:
                    raw_return = -slippage / price  # negative slippage = cost
                    correct_direction = raw_return >= 0 if side == "BUY" else raw_return <= 0
                    engine.record_trade_result(raw_return)
                    engine.record_prediction(correct_direction, raw_return)
                continue

            # ----------------------------------------------------------------
            # trade_signals: apply risk governance before forwarding
            # ----------------------------------------------------------------
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
            price = float(data.get("price", 0) or 0)
            if price <= 0:
                logger.error(f"Signal missing valid price: {data}")
                continue

            stop_loss = price * (0.98 if data.get("signal") == "BUY" else 1.02)
            units = engine.calculate_position_size(price, stop_loss)

            if units <= 0:
                logger.info(f"Position size=0 for {data.get('symbol')} — skipping.")
                continue

            # 4. Forward approved execution request
            execution_payload = {
                "model_id": data.get("model_id", "unknown"),
                "symbol": data["symbol"],
                "qty": units,
                "side": "buy" if data.get("signal") == "BUY" else "sell",
                "type": "market",
                "confidence": data.get("confidence", 0.0),
                "explanation": data.get("explanation", []),
                "timestamp": data.get("timestamp"),
            }
            await r.publish("execution_requests", json.dumps(execution_payload))
            logger.info(
                f"Approved → {execution_payload['side'].upper()} "
                f"{units} {execution_payload['symbol']}"
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("RiskGuardian stopped.")
