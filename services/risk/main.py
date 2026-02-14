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

    # TODO: Connect to Redis to listen for:
    # 1. Account Updates (Equity/PnL)
    # 2. Trade Signals (for validation)
    
    logger.info("Listening for events...")
    while True:
        # Mock loop
        if engine.check_kill_switch():
            # TODO: Emit LIQUIDATE_ALL event to Execution Service
            pass
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("RiskGuardian stopped.")
