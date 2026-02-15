import asyncio
import os
import logging
import sys
from dotenv import load_dotenv
from risk_engine import RiskEngine

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanRiskGuardian")

async def main():
    logger.info("Starting TitanFlow RiskGuardian...")
    
    # Load Config
    config = {
        "MAX_DAILY_LOSS_PCT": float(os.getenv("RISK_MAX_DAILY_LOSS", 0.03)),
        "RISK_PER_TRADE_PCT": float(os.getenv("RISK_PER_TRADE", 0.01))
    }
    
    engine = RiskEngine(config)
    logger.info(f"Risk Engine initialized with Max Drawdown: {config['MAX_DAILY_LOSS_PCT']:.1%}")

    # Connect to Redis
    try:
        r = redis.from_url(f"redis://{os.getenv('REDIS_HOST', 'redis')}:6379")
        await r.ping()
        pubsub = r.pubsub()
        await pubsub.subscribe("trade_signals")
        logger.info("Connected to Redis and subscribed to 'trade_signals'")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return

    logger.info("Listening for events...")
    
    async for message in pubsub.listen():
        try:
            if message['type'] != 'message':
                continue
                
            data = json.loads(message['data'])
            logger.info(f"Received Signal: {data}")
            
            # 1. Validate Signal
            if not engine.validate_signal(data):
                continue
                
            # 2. Check Kill Switch
            if engine.check_kill_switch():
                # TODO: Send liquidate command
                logger.warning("Kill Switch Triggered - Ignoring Signal")
                continue
                
            # 3. Calculate Size
            # entry_price = data['price']
            # stop_loss = entry_price * 0.98 if data['signal'] == 'BUY' else entry_price * 1.02
            # For MVP, using simple Risk Engine logic
            # risk_engine.py needs 'entry_price' and 'stop_loss' to calc size via 'risk_per_trade'
            # Let's assume a default 2% stop loss for now
            
            price = float(data.get('price', 0))
            if price == 0:
                logger.error("Signal missing price")
                continue
                
            stop_loss = price * (0.98 if data['signal'] == 'BUY' else 1.02)
            
            units = engine.calculate_position_size(price, stop_loss)
            
            if units > 0:
                execution_payload = {
                    "symbol": data['symbol'],
                    "qty": units,
                    "side": "buy" if data['signal'] == 'BUY' else "sell",
                    "type": "market",
                    "timestamp": data.get("timestamp")
                }
                
                await r.publish("execution_requests", json.dumps(execution_payload))
                logger.info(f"Published Execution Request: {execution_payload['symbol']} {execution_payload['side']} {units}")
            else:
                logger.info(f"Calculated position size is 0 for {data['symbol']}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")

        # Keep the heartbeat check?
        # await asyncio.sleep(0.01) # Small sleep to prevent tight loop if needed, but pubsub.listen is async generator

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("RiskGuardian stopped.")
