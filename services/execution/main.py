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

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanExecutionService")

# --- Helper Functions for Paper Execution ---

def simulate_fill(signal: Dict, current_price: float, manager: PortfolioManager) -> Optional[Dict]:
    """
    Simulates a trade execution for paper mode.
    Returns a Fill Event dictionary if successful, None otherwise.
    """
    model_id = signal.get("model_id", "default_model")
    side = signal.get("signal")
    symbol = signal.get("symbol")
    # Paper Mode: Use signal price or current market price
    price = float(signal.get("price") or current_price or 0.0)
    
    if price <= 0:
        return None

    # Get or Create Portfolio
    # Note: In a real system, we might require pre-registration. 
    # Here we auto-create for smoother dev experience.
    portfolio = manager.get_portfolio(model_id)
    if not portfolio:
        portfolio = manager.create_portfolio(model_id)

    # Basic Risk/Budget Check
    # For MVP, allocate fixed amount or % of cash?
    # Old logic: budget = min(cash, equity * risk * confidence)
    # Simplified: Invest $10k per trade or max cash
    trade_amount = 10000.0 
    
    qty = 0
    if side == "BUY":
        if portfolio.cash < 10.0: # Minimum cash needed
            return None
        actual_amount = min(portfolio.cash, trade_amount)
        qty = int(actual_amount / price)
        if qty <= 0:
            return None
    elif side == "SELL":
        # Check current position
        current_pos = portfolio.positions.get(symbol)
        if not current_pos or current_pos['qty'] <= 0:
            return None
        qty = current_pos['qty'] # Sell all for now (simplify)

    if qty <= 0:
        return None
        
    return {
        "id": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "model_id": model_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "FILLED",
        "mode": "paper"
    }

async def publish_portfolios(redis_client, manager: PortfolioManager):
    """Publish leaderboard/portfolio summaries to Redis."""
    portfolios = manager.get_all_portfolios()
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
    logger.info("Live execution not yet fully implemented. Creating placeholder.")
    # ... (Keep existing live logic logic if needed, but for now we focus on Paper)
    pass

async def run_paper_execution(redis_client):
    manager = PortfolioManager()
    
    # Configuration
    starting_cash = float(os.getenv("PAPER_STARTING_CASH", "100000"))
    publish_interval = float(os.getenv("PAPER_PORTFOLIO_PUBLISH_SECONDS", "2"))
    
    # Redis Channels
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("trade_signals", "market_data")
    logger.info("Execution mode=paper. Listening for signals...")

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
                    # Update equity for all portfolios
                    # Note: strict `calculate_total_equity` might need `current_prices` passing down
                    # For now `get_all_portfolios` implementation in manager might need adjustment 
                    # OR we pass prices here.
                    # Let's patch manager.get_all_portfolios to accept prices? 
                    # Or just do it here. 
                    
                    # Hack: Attach prices to manager instance temporarily or pass to methods
                    # Let's rely on manager having a way to know prices.
                    # Actually, let's just make get_all_portfolios do the calc if we pass prices
                    # We will update manager.get_all_portfolios signature in next step if needed.
                    # For now, let's assume it works or we fix it.
                    
                    await publish_portfolios(redis_client, manager)
                    last_publish_at = now
                
            elif channel == "trade_signals":
                # 1. Received Signal
                logger.info(f"Received Signal: {payload}")
                symbol = payload.get("symbol")
                price = current_prices.get(symbol, 0.0)
                
                # 2. Simulate Execution (Broker Step)
                fill = simulate_fill(payload, price, manager)
                
                if fill:
                    # 3. Update Portfolio (Legder Step)
                    manager.on_execution_fill(fill)
                    
                    # 4. Publish Fill Event (for Dashboard/Logs)
                    await redis_client.publish("execution_filled", json.dumps(fill))
                    logger.info(f"Executed Paper Trade: {fill['side']} {fill['qty']} {fill['symbol']} @ {fill['price']}")

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
