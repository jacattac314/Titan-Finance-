import logging
import asyncio
import numpy as np
import pandas as pd
import torch
from typing import Dict, Any, Optional, Deque
from collections import deque
from .base import Strategy
from feature_engineering import FeatureEngineer
from models.tft_model import TFTModel

logger = logging.getLogger("TitanTFT")

class TFTStrategy(Strategy):
    """
    Temporal Fusion Transformer (TFT) Strategy.
    Predicts next 5 bars relative price movement.
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lookback = config.get("lookback", 60)
        self.device = torch.device("cpu")
        self.output_horizon = 60  # 60 x 1-min bars = 1 hour forecast
        
        # Warmup
        self.warmup_period = 200
        self.prices: Deque[float] = deque(maxlen=self.warmup_period)
        
        # Feature Engineering
        self.fe = FeatureEngineer()
        
        # Model
        self.model = TFTModel(input_size=14, d_model=64, num_layers=2, output_horizon=self.output_horizon)
        
        # Load Trained Weights
        import os
        self.weights_path = os.path.join(os.path.dirname(__file__), '../models/weights/tft_weights.pth')
        
        if os.path.exists(self.weights_path):
            try:
                self.model.load_state_dict(torch.load(self.weights_path, map_location=self.device, weights_only=True))
                logger.info(f"Loaded TFT weights from {self.weights_path}.")
            except Exception as e:
                logger.error(f"Failed to load weights: {e}")
        else:
            logger.warning(f"TFT weights not found at {self.weights_path}. Running with random initialization.")
            
        self.model.eval()
        self.model.to(self.device)
        
        logger.info(f"Initialized TFT Strategy for {self.symbol}. Waiting for {self.warmup_period} bars.")

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        price = float(tick["price"])
        self.prices.append(price)
        
        if len(self.prices) < self.warmup_period:
            return None

        # Create DataFrame from buffer
        df = pd.DataFrame({
            "open": list(self.prices),
            "high": list(self.prices),
            "low": list(self.prices),
            "close": list(self.prices),
            "volume": [1000] * len(self.prices)
        })
        
        # Features
        df = self.fe.calculate_features(df)
        df.dropna(inplace=True)
        
        if len(df) < self.lookback:
            return None

        # Prepare Input
        cols = ['open', 'high', 'low', 'close', 'volume', 'RSI', 'MACD', 'MACD_line', 'MACD_signal', 'log_ret', 'ATR', 'BBU', 'BBL', 'BBM']
        # Select available columns (expecting all 14)
        available_cols = [c for c in cols if c in df.columns]
        recent_data = df[available_cols].iloc[-self.lookback:].values # [60, 14]
        
        # Scale (using simple standardization, same as training script)
        mean = np.mean(recent_data, axis=0)
        std = np.std(recent_data, axis=0) + 1e-8
        scaled_data = (recent_data - mean) / std
        
        tensor_in = torch.FloatTensor(scaled_data).unsqueeze(0).to(self.device) # [1, 60, 14]
        
        # Inference
        with torch.no_grad():
            # Output is [1, 5] (predictions for next 5 steps in scaled space)
            predictions = self.model(tensor_in).squeeze(0).cpu().numpy() # [60]
            
        # Interpret
        # The model was trained to predict the scaled 'close' price.
        close_idx = available_cols.index('close')
        current_scaled_close = scaled_data[-1, close_idx]
        
        # Use the final prediction (t+60) as the 1-hour forecast
        final_prediction_scaled = predictions[-1]
        avg_prediction = np.mean(predictions)
        
        # Un-scale the final prediction to get an actual price forecast
        forecast_price = float(final_prediction_scaled * std[close_idx] + mean[close_idx])
        forecast_timestamp = int(tick.get("timestamp", 0)) + (60 * 60 * 1000)  # +1 hour in ms
        
        # Simple Logic: If model predicts values > current scaled close + threshold
        signal = None
        confidence = 0.5
        
        # 0.1 standard deviations in z-score space
        if avg_prediction > current_scaled_close + 0.1: 
            signal = "BUY"
            confidence = min(0.5 + (avg_prediction - current_scaled_close), 0.99)
        elif avg_prediction < current_scaled_close - 0.1:
            signal = "SELL"
            confidence = min(0.5 + (current_scaled_close - avg_prediction), 0.99)
            
        if signal:
            return {
                "model_id": self.model_id,
                "model_name": "TFT_Transformer_v1",
                "symbol": self.symbol,
                "signal": signal,
                "confidence": round(confidence, 2),
                "price": price,
                "timestamp": tick.get("timestamp"),
                "explanation": [f"Forecast_1H_Z: {final_prediction_scaled:.2f}"],
                "forecast_price": round(forecast_price, 2),
                "forecast_timestamp": forecast_timestamp
            }
            
        return None

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None
