import asyncio
import os
import logging
import sys
import torch
import numpy as np
from dotenv import load_dotenv

from feature_engineering import FeatureEngineer
from model import load_model
from explainability import XAIEngine
from db import db

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TitanSignalEngine")

# Simple watchlist for MVP
WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "TSLA", "NVDA", "AMD", "AMZN"]
# Thresholds
BUY_THRESHOLD = 0.7
SELL_THRESHOLD = 0.7

async def process_symbol(symbol: str, fe: FeatureEngineer, model, xai: XAIEngine):
    """Process a single symbol: Fetch -> Feature -> Model -> Signal."""
    try:
        # 1. Fetch Data (Need window_size + lookback for indicators)
        # 60 (window) + 30 (indicators) = 90
        raw_data = await db.fetch_ohlcv(symbol, limit=100)
        
        if not raw_data or len(raw_data) < 90:
            # logger.debug(f"Insufficient data for {symbol}")
            return
            
        # 2. Prepare Features
        # Returns (1, Seq, Features)
        input_tensor_np = fe.prepare_batch(raw_data)
        
        if input_tensor_np is None:
            return

        # Convert to Tensor
        input_tensor = torch.from_numpy(input_tensor_np).float()
        
        # 3. Inference
        with torch.no_grad():
            logits = model(input_tensor) # (1, 3)
            probs = logits.squeeze(0).numpy() # [Buy, Hold, Sell]
            
        buy_prob, hold_prob, sell_prob = probs[0], probs[1], probs[2]
        
        signal = None
        confidence = 0.0
        
        if buy_prob > BUY_THRESHOLD:
            signal = "BUY"
            confidence = float(buy_prob)
        elif sell_prob > SELL_THRESHOLD:
            signal = "SELL"
            confidence = float(sell_prob)
            
        if signal:
            logger.info(f"SIGNAL DETECTED: {symbol} {signal} ({confidence:.2f})")
            
            # 4. Explainability
            explanation = []
            if xai:
                try:
                    shap_values = xai.explain_prediction(input_tensor)
                    # Class index: 0=Buy, 1=Hold, 2=Sell (Depends on training mapping, assuming this for now)
                    target_class = 0 if signal == "BUY" else 2
                    
                    # Feature names from DF columns (need to expose this from fe)
                    # For now, using generic names or reconstructing
                    feat_names = ['log_ret', 'rsi', 'atr', 'MACD', 'MACDh', 'MACDs', 'BBU', 'BBL']
                    
                    explanation = xai.get_top_features(shap_values, feat_names, class_idx=target_class)
                except Exception as e:
                    logger.warning(f"XAI failed: {e}")
            
            # 5. Publish
            payload = {
                "symbol": symbol,
                "signal": signal,
                "confidence": confidence,
                "explanation": explanation,
                "timestamp": raw_data[-1]['timestamp'] # timestamp of last bar
            }
            await db.publish_signal(payload)
            
    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")

async def main():
    logger.info("Starting TitanFlow SignalEngine...")
    
    # 1. Initialize Components
    await db.connect()
    
    fe = FeatureEngineer(window_size=60)
    
    # Input dim: 8 (log_ret, rsi, atr, macd*3, bb*2)
    model = load_model(input_dim=8) 
    
    # Initialize XAI with dummy background data for now
    # In prod, load a representative dataset
    background_data = np.zeros((10, 60, 8)) 
    xai = XAIEngine(model, background_data)
    
    logger.info("Engine Initialized. Entering Loop...")
    
    try:
        while True:
            tasks = [process_symbol(sym, fe, model, xai) for sym in WATCHLIST]
            await asyncio.gather(*tasks)
            
            # Sleep for 1 minute (aligned to next minute ideally)
            await asyncio.sleep(60)
            
    except Exception as e:
        logger.error(f"Main loop crashed: {e}")
    finally:
        await db.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SignalEngine stopped.")
