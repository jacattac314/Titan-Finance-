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

async def simulate_fill(signal: Dict, current_price: float, manager: PortfolioManager) -> Optional[Dict]:
    """
    Simulates a trade execution for paper mode.
    Returns a Fill Event dictionary if successful, None otherwise.
    """
    model_id = signal.get("model_id", "default_model")
    # Support both execution_requests ("side": "buy"/"sell") and legacy trade_signals ("signal": "BUY"/"SELL")
    side = (signal.get("side") or signal.get("signal") or "").upper()
    symbol = signal.get("symbol")
    # Paper Mode: Use signal price or current market price
    decision_price = float(signal.get("price") or current_price or 0.0)

    if decision_price <= 0:
        return None

    # Get or Create Portfolio
    portfolio = manager.get_portfolio(model_id)
    if not portfolio:
        portfolio = manager.create_portfolio(model_id)

    # Prefer risk-calculated qty from execution_requests; fall back to internal sizing
    risk_qty = signal.get("qty")
    trade_amount = 10000.0
    qty = 0
    if side == "BUY":
        if portfolio.cash < 10.0:
            return None
        if risk_qty:
            qty = int(risk_qty)
        else:
            actual_amount = min(portfolio.cash, trade_amount)
            qty = int(actual_amount / decision_price)
    elif side == "SELL":
        current_pos = portfolio.positions.get(symbol)
        if not current_pos or current_pos['qty'] <= 0:
            return None
        qty = int(risk_qty) if risk_qty else current_pos['qty']

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
        "explanation": signal.get("explanation", [])
    }

async def publish_portfolios(redis_client, manager: PortfolioManager, current_prices: Dict[str, float] = None):
    """Publish leaderboard/portfolio summaries to Redis."""
    portfolios = manager.get_all_portfolios(current_prices)
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

    # --- Subscribe to channels ---
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("execution_requests", "market_data", "risk_commands")
    logger.info("Live execution subscribed to [execution_requests, market_data, risk_commands].")

    async for message in pubsub.listen():
        try:
            if message.get("type") != "message":
                continue

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

            # ---- Risk-approved execution request ----
            elif channel == "execution_requests":
                model_id = payload.get("model_id", "unknown")
                symbol = payload.get("symbol", "")
                # execution_requests uses "side": "buy"/"sell"; normalise to "BUY"/"SELL"
                signal_str = (payload.get("side") or payload.get("signal") or "HOLD").upper()
                confidence = float(payload.get("confidence", 0.0))
                explanation = payload.get("explanation", [])
                price = current_prices.get(symbol, float(payload.get("price", 0) or 0))

                logger.info(
                    f"Execution request [{model_id}]: {signal_str} {symbol} "
                    f"conf={confidence:.2%} price={price}"
                )

                # 1. Audit the risk-approved request
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
                    await redis_client.publish("execution_filled", json.dumps({
                        **result,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "mode": "live",
                    }))

            # ---- Risk commands (kill-switch, manual approval) ----
            elif channel == "risk_commands":
                command = payload.get("command")
                if command == "LIQUIDATE_ALL":
                    logger.critical(
                        f"RISK_COMMAND: LIQUIDATE_ALL — "
                        f"reason={payload.get('reason', 'unknown')}"
                    )
                    connector.activate_kill_switch()
                    connector.liquidate_all()
                    await audit.log_kill_switch(
                        trigger=f"risk_commands: {payload.get('reason', 'unknown')}",
                        drawdown_pct=0.0,
                        equity=0.0,
                        model_version=model_version,
                    )
                elif command == "ACTIVATE_MANUAL_APPROVAL":
                    logger.warning(
                        f"RISK_COMMAND: ACTIVATE_MANUAL_APPROVAL — "
                        f"sharpe={payload.get('rolling_sharpe')} "
                        f"accuracy={payload.get('rolling_accuracy')}"
                    )
                    connector.set_manual_approval(True)

        except Exception as exc:
            logger.error(f"Error in live execution loop: {exc}")

async def run_paper_execution(redis_client):
    manager = PortfolioManager()
    
    # Configuration
    starting_cash = float(os.getenv("PAPER_STARTING_CASH", "100000"))
    publish_interval = float(os.getenv("PAPER_PORTFOLIO_PUBLISH_SECONDS", "2"))
    
    # Redis Channels
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("execution_requests", "market_data", "risk_commands")
    logger.info("Execution mode=paper. Subscribed to [execution_requests, market_data, risk_commands].")

    last_publish_at = 0.0
    current_prices = {} # symbol -> price

    async for message in pubsub.listen():
        try:
            if message.get("type") != "message":
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
                
            elif channel == "execution_requests":
                # 1. Received risk-approved request
                logger.info(f"Execution request: {payload}")
                symbol = payload.get("symbol")
                price = current_prices.get(symbol, 0.0)

                # 2. Simulate Execution (Broker Step) with Async Latency
                fill = await simulate_fill(payload, price, manager)

                if fill:
                    # 3. Update Portfolio (Ledger Step)
                    manager.on_execution_fill(fill)

                    # 4. Publish Fill Event (for Dashboard/Risk feedback loop)
                    await redis_client.publish("execution_filled", json.dumps(fill))
                    logger.info(f"Executed ({fill['slippage']}): {fill['side']} {fill['qty']} {fill['symbol']} @ {fill['price']}")

            elif channel == "risk_commands":
                command = payload.get("command")
                if command == "LIQUIDATE_ALL":
                    logger.critical(
                        f"RISK_COMMAND: LIQUIDATE_ALL (paper) — "
                        f"reason={payload.get('reason', 'unknown')}"
                    )
                    # In paper mode: log each portfolio as halted (full liquidation
                    # logic to be implemented in Phase 2 order-lifecycle work)
                    for portfolio_id in list(manager.portfolios.keys()):
                        logger.warning(f"Paper liquidation: halting portfolio {portfolio_id}")
                elif command == "ACTIVATE_MANUAL_APPROVAL":
                    logger.warning(
                        f"RISK_COMMAND: ACTIVATE_MANUAL_APPROVAL (paper) — "
                        f"sharpe={payload.get('rolling_sharpe')} "
                        f"accuracy={payload.get('rolling_accuracy')}"
                    )

        except Exception as exc:
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
