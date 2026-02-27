import asyncio
import datetime
import json
import logging
import os
import sys
import uuid
from typing import Dict, Optional

import redis.asyncio as redis
from dotenv import load_dotenv

# New Core Imports
from core.manager import PortfolioManager
from core.portfolio import VirtualPortfolio
from risk.validator import OrderValidator
from simulation.slippage import SlippageModel
from simulation.latency import LatencySimulator

# Alpaca live-execution connector and audit logger
from alpaca_client import TitanAlpacaConnector
from audit import TradeAuditLogger

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanExecutionService")

# Initialize Engines
validator = OrderValidator()
slippage_model = SlippageModel()
latency_sim = LatencySimulator()

# --- Helper Functions for Paper Execution ---

async def simulate_fill(execution_req: Dict, current_price: float, manager: PortfolioManager, kill_switch_active: bool = False) -> Optional[Dict]:
    """
    Simulates a trade execution for paper mode.
    Expects an execution_requests payload (risk-approved) with pre-calculated qty.
    Returns a Fill Event dictionary if successful, None otherwise.
    """
    if kill_switch_active:
        logger.warning("Paper fill rejected — kill switch is active.")
        return None

    model_id = execution_req.get("model_id", "default_model")
    # Risk service publishes side as lowercase "buy"/"sell"
    side = execution_req.get("side", "").upper()
    symbol = execution_req.get("symbol")
    # Use risk-calculated qty; qty is pre-sized by RiskGuardian
    qty = int(execution_req.get("qty", 0))
    # Use current market price; execution_requests may not include price
    decision_price = float(execution_req.get("price") or current_price or 0.0)

    if decision_price <= 0 or qty <= 0 or side not in ("BUY", "SELL"):
        return None

    # Get or Create Portfolio
    portfolio = manager.get_portfolio(model_id)
    if not portfolio:
        portfolio = manager.create_portfolio(model_id)

    # Local sanity checks
    if side == "BUY" and portfolio.cash < 10.0:
        return None
    if side == "SELL":
        current_pos = portfolio.positions.get(symbol)
        if not current_pos or current_pos.get("qty", 0) <= 0:
            return None
        qty = current_pos["qty"]  # always sell the full position

    if qty <= 0:
        return None

    # 1. RISK CHECK
    if not validator.validate(portfolio, symbol, decision_price, qty, side):
        return None

    # 2. LATENCY SIMULATION
    await latency_sim.delay()

    # 3. SLIPPAGE CALCULATION
    executed_price = slippage_model.calculate_price(decision_price, side, qty)

    # 4. EXECUTION
    return {
        "id": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "model_id": model_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": executed_price,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "FILLED",
        "mode": "paper",
        "slippage": round(executed_price - decision_price, 4),
        "explanation": execution_req.get("explanation", [])
    }

async def publish_portfolios(redis_client, manager: PortfolioManager, current_prices: Dict[str, float] = None):
    """Publish leaderboard/portfolio summaries to Redis."""
    portfolios = manager.get_all_portfolios(current_prices or {})
    # Sort by equity (descending)
    portfolios.sort(key=lambda x: x['equity'], reverse=True)
    
    payload = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "best_model": portfolios[0]["id"] if portfolios else None,
        "models": portfolios,
        "mode": "paper",
    }
    await redis_client.publish("paper_portfolio_updates", json.dumps(payload))

# --- Main Execution Loops ---

async def run_live_execution(redis_client):
    """
    Live execution loop — connects Titan ML signals to real Alpaca orders.

    Flow per received trade_signal:
        1. Audit-log the raw signal (provenance record).
        2. Check kill switch state.
        3. Route to TitanAlpacaConnector.execute_signal().
        4. Audit-log the submitted order.
        5. Periodically poll Alpaca account equity and trigger circuit breaker
           if daily drawdown exceeds CIRCUIT_BREAKER_DRAWDOWN_PCT.
        6. Activate manual-approval mode if ROLLBACK_MIN_SHARPE threshold
           is monitored and falls below the configured floor.
    """
    logger.info("Starting LIVE execution engine...")

    # --- Configuration ---
    model_version = os.getenv("MODEL_VERSION", "v1.0")
    circuit_breaker_drawdown = float(os.getenv("CIRCUIT_BREAKER_DRAWDOWN_PCT", "0.03"))
    rollback_min_sharpe = float(os.getenv("ROLLBACK_MIN_SHARPE", "0.5"))
    account_poll_interval = float(os.getenv("ACCOUNT_POLL_SECONDS", "30"))

    # --- Initialise connector (singleton) ---
    try:
        connector = TitanAlpacaConnector.get_instance()
    except ValueError as exc:
        logger.error(f"Cannot start live execution — connector init failed: {exc}")
        return

    # --- Initialise audit logger and wire up Redis ---
    audit = TradeAuditLogger.get_instance()
    audit.set_redis_client(redis_client)

    # Snapshot starting equity for drawdown calculation
    account_info = connector.get_account()
    starting_equity: float = account_info.get("equity", 0.0)
    if starting_equity <= 0:
        logger.error("Could not retrieve starting equity from Alpaca. Aborting live mode.")
        return
    logger.info(f"Starting equity: ${starting_equity:,.2f}")

    last_account_poll = 0.0
    current_prices: Dict[str, float] = {}

    # --- Subscribe to channels — only risk-approved requests, never raw trade_signals ---
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("execution_requests", "market_data")
    logger.info("Live execution subscribed to [execution_requests, market_data].")

    _HEARTBEAT_INTERVAL = 30  # seconds
    last_heartbeat = asyncio.get_running_loop().time()

    while True:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        except (Exception,) as conn_exc:
            logger.error(f"Redis connection lost in live execution: {conn_exc}. Reconnecting in 5s...")
            await asyncio.sleep(5)
            try:
                pubsub = redis_client.pubsub()
                await pubsub.subscribe("execution_requests", "market_data")
                last_heartbeat = asyncio.get_running_loop().time()
                logger.info("Live execution reconnected to Redis.")
            except Exception as reconnect_exc:
                logger.error(f"Reconnect failed: {reconnect_exc}")
            continue

        now_hb = asyncio.get_running_loop().time()
        if now_hb - last_heartbeat >= _HEARTBEAT_INTERVAL:
            try:
                await redis_client.ping()
            except Exception:
                pass
            last_heartbeat = now_hb

        if message is None:
            continue

        try:
            channel = message.get("channel", b"")
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")

            payload = json.loads(message["data"])
            now = asyncio.get_running_loop().time()

            # ---- Market data: keep price cache fresh ----
            if channel == "market_data":
                if payload.get("type") == "trade":
                    current_prices[payload["symbol"]] = float(payload["price"])

                # Periodic account poll → circuit breaker check
                if (now - last_account_poll) >= account_poll_interval:
                    last_account_poll = now
                    acct = connector.get_account()
                    if acct:
                        equity = acct.get("equity", starting_equity)
                        unrealized_pl = acct.get("unrealized_pl", 0.0)
                        daily_return = unrealized_pl / starting_equity if starting_equity > 0 else 0.0

                        logger.info(
                            f"Account poll — equity=${equity:,.2f} "
                            f"daily_pnl=${unrealized_pl:+,.2f} ({daily_return:+.2%})"
                        )

                        # --- Circuit breaker: drawdown limit ---
                        if daily_return <= -circuit_breaker_drawdown and not connector.is_blocked:
                            trigger_msg = (
                                f"Daily drawdown {daily_return:.2%} exceeded limit "
                                f"-{circuit_breaker_drawdown:.2%}"
                            )
                            logger.critical(trigger_msg)
                            connector.activate_kill_switch()
                            connector.liquidate_all()
                            await audit.log_kill_switch(
                                trigger=trigger_msg,
                                drawdown_pct=daily_return,
                                equity=equity,
                                model_version=model_version,
                            )

            # ---- Risk-approved execution request: execute via Alpaca ----
            elif channel == "execution_requests":
                model_id = payload.get("model_id", "unknown")
                symbol = payload.get("symbol", "")
                signal_str = payload.get("side", "hold").upper()  # risk sends "buy"/"sell"
                confidence = float(payload.get("confidence", 0.0))
                explanation = payload.get("explanation", [])
                price = current_prices.get(symbol, float(payload.get("price", 0) or 0))

                logger.info(
                    f"Signal received [{model_id}]: {signal_str} {symbol} "
                    f"conf={confidence:.2%} price={price}"
                )

                # 1. Audit the raw signal
                await audit.log_signal(
                    model_id=model_id,
                    model_version=model_version,
                    symbol=symbol,
                    signal=signal_str,
                    confidence=confidence,
                    price=price,
                    explanation=explanation,
                )

                # 2. Execute (connector handles all gates internally)
                result = connector.execute_signal(
                    symbol=symbol,
                    signal=signal_str,
                    confidence=confidence,
                    model_id=model_id,
                    price=price,
                    model_version=model_version,
                )

                # 3. Audit the order if one was submitted
                if result:
                    await audit.log_order(
                        model_id=result["model_id"],
                        model_version=result["model_version"],
                        symbol=result["symbol"],
                        side=result["side"],
                        qty=result["qty"],
                        price=result["price_at_signal"],
                        confidence=result["confidence"],
                        order_id=result["order_id"],
                        status=result["status"],
                        mode=result["mode"],
                    )
                    # Publish fill-like event for dashboard compatibility
                    await redis_client.publish("execution_filled", json.dumps({
                        **result,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "mode": "live",
                    }))

        except Exception as exc:
            logger.error(f"Error in live execution loop: {exc}")

async def run_paper_execution(redis_client):
    manager = PortfolioManager()

    # Configuration
    starting_cash = float(os.getenv("PAPER_STARTING_CASH", "100000"))
    publish_interval = float(os.getenv("PAPER_PORTFOLIO_PUBLISH_SECONDS", "2"))

    # Redis Channels — consume risk-approved requests, market data, and risk commands
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("execution_requests", "market_data", "risk_commands")
    logger.info("Execution mode=paper. Listening for risk-approved execution requests...")

    last_publish_at = 0.0
    current_prices: Dict[str, float] = {}
    kill_switch_active = False

    while True:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue

            channel = message.get("channel")
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")

            payload = json.loads(message["data"])
            now = asyncio.get_running_loop().time()

            if channel == "market_data":
                # Update internal price cache
                if payload.get("type") == "trade":
                    current_prices[payload["symbol"]] = float(payload["price"])

                # Periodically publish portfolio updates
                if (now - last_publish_at) >= publish_interval:
                    await publish_portfolios(redis_client, manager, current_prices)
                    last_publish_at = now

            elif channel == "risk_commands":
                command = payload.get("command")
                if command == "LIQUIDATE_ALL":
                    kill_switch_active = True
                    logger.warning(f"Kill switch activated via risk_commands: {payload.get('reason')}")
                elif command in ("RESET_KILL_SWITCH", "RESUME_TRADING"):
                    kill_switch_active = False
                    logger.info("Kill switch cleared via risk_commands.")

            elif channel == "execution_requests":
                # 1. Received risk-approved execution request
                logger.info(f"Received execution request: {payload}")
                symbol = payload.get("symbol")
                price = current_prices.get(symbol, 0.0)

                # 2. Simulate Execution (Broker Step) with Async Latency
                fill = await simulate_fill(payload, price, manager, kill_switch_active)

                if fill:
                    # 3. Update Portfolio (Ledger Step)
                    manager.on_execution_fill(fill)

                    # 4. Publish Fill Event (for Dashboard/Logs)
                    await redis_client.publish("execution_filled", json.dumps(fill))
                    logger.info(f"Executed ({fill['slippage']}): {fill['side']} {fill['qty']} {fill['symbol']} @ {fill['price']}")

        except (Exception,) as exc:
            logger.error(f"Error in paper execution loop: {exc}")

async def main():
    logger.info("Starting TitanFlow TradeExecutor...")
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_client = redis.from_url(f"redis://{redis_host}:6379")

    try:
        await redis_client.ping()
    except Exception as exc:
        logger.error(f"Failed to connect to Redis: {exc}")
        return

    execution_mode = os.getenv("EXECUTION_MODE", "paper").strip().lower()
    if execution_mode == "live":
        await run_live_execution(redis_client)
    else:
        await run_paper_execution(redis_client)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("TradeExecutor stopped.")
