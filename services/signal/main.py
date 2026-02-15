import asyncio
import os
import logging
import sys
import torch
import numpy as np
from datetime import datetime, timezone
from dotenv import load_dotenv

from feature_engineering import FeatureEngineer
from model import load_model
from explainability import XAIEngine
from strategies import RSIMeanReversion, SMACrossover
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


def _format_timestamp(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return datetime.now(timezone.utc).isoformat()


def _build_hybrid_signal(probs):
    buy_prob, _, sell_prob = probs[0], probs[1], probs[2]
    if buy_prob > BUY_THRESHOLD:
        return "BUY", float(buy_prob)
    if sell_prob > SELL_THRESHOLD:
        return "SELL", float(sell_prob)
    return None, 0.0


async def process_symbol(symbol: str, fe: FeatureEngineer, model, xai: XAIEngine, baseline_strategies):
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
            
        latest_price = float(raw_data[-1]["close"])
        timestamp = _format_timestamp(raw_data[-1].get("timestamp"))

        # 4. Multi-model signal generation
        signals_to_publish = []

        hybrid_signal, hybrid_confidence = _build_hybrid_signal(probs)
        if hybrid_signal:
            explanation = []
            if xai:
                try:
                    shap_values = xai.explain_prediction(input_tensor)
                    target_class = 0 if hybrid_signal == "BUY" else 2
                    feat_names = ['log_ret', 'rsi', 'atr', 'MACD', 'MACDh', 'MACDs', 'BBU', 'BBL']
                    explanation = xai.get_top_features(shap_values, feat_names, class_idx=target_class)
                except Exception as e:
                    logger.warning(f"XAI failed: {e}")

            signals_to_publish.append({
                "symbol": symbol,
                "signal": hybrid_signal,
                "confidence": hybrid_confidence,
                "price": latest_price,
                "explanation": explanation,
                "timestamp": timestamp,
                "model_id": "hybrid_ai",
                "model_name": "Hybrid AI"
            })

        for strategy in baseline_strategies:
            decision = strategy.generate_signal(raw_data)
            if not decision:
                continue
            signals_to_publish.append({
                "symbol": symbol,
                "signal": decision.signal,
                "confidence": decision.confidence,
                "price": latest_price,
                "explanation": decision.explanation,
                "timestamp": timestamp,
                "model_id": strategy.model_id,
                "model_name": strategy.model_name
            })

        for payload in signals_to_publish:
            logger.info(
                "SIGNAL DETECTED: %s %s (%s %.2f)",
                payload["symbol"],
                payload["signal"],
                payload["model_id"],
                payload["confidence"],
            )
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
    baseline_strategies = [
        SMACrossover(short_window=10, long_window=30),
        RSIMeanReversion(window=14, oversold=30, overbought=70),
    ]
    
    # Initialize XAI with dummy background data for now
    # In prod, load a representative dataset
    background_data = np.zeros((10, 60, 8)) 
    xai = XAIEngine(model, background_data)
    
    logger.info("Engine Initialized. Entering Loop...")
    
    try:
        while True:
            tasks = [process_symbol(sym, fe, model, xai, baseline_strategies) for sym in WATCHLIST]
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
