import asyncio
import os
import logging
import sys
from dotenv import load_dotenv
from alpaca_executor import AlpacaExecutor

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanExecutionService")

async def main():
    logger.info("Starting TitanFlow TradeExecutor...")
    
    try:
        executor = AlpacaExecutor()
        acct = await executor.get_account()
        logger.info(f"Connected to Broker. Buying Power: ${acct.buying_power}")
    except Exception as e:
        logger.error(f"Failed to initialize Executor: {e}")
        return

    # TODO: Listen to Redis 'execution_requests' channel
    
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("TradeExecutor stopped.")
