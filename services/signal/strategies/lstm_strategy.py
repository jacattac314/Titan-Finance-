import logging
import os
import asyncio
import numpy as np
import pandas as pd
import torch
from typing import Dict, Any, Optional, Deque
from collections import deque
from .base import Strategy
from feature_engineering import FeatureEngineer
from models.lstm_model import LSTMModel

logger = logging.getLogger("TitanLSTM")

class LSTMStrategy(Strategy):
    """
    Deep Learning Strategy using LSTM + Attention.
    Predicts next bar direction based on a lookback window of 60 bars.
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lookback = config.get("lookback", 60)
        self.device = torch.device("cpu") # use cpu for inference in this container
        
        # Data Buffer
        # We need enough data for feature engineering + lookback
        self.warmup_period = 200 
        self.prices: Deque[float] = deque(maxlen=self.warmup_period)
        self.data_buffer: Deque[Dict] = deque(maxlen=self.warmup_period)
        
        # Feature Engineering
        self.fe = FeatureEngineer()
        
        # Model
        self.model = LSTMModel(input_size=14, hidden_size=64, num_layers=2)
        self.model_path = config.get("model_path") or os.getenv("LSTM_MODEL_PATH", "")
        if self.model_path and os.path.isfile(self.model_path):
            try:
                self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
                logger.info(f"LSTM weights loaded from '{self.model_path}'.")
            except Exception as exc:
                logger.warning(
                    f"Failed to load LSTM weights from '{self.model_path}': {exc}. "
                    "Using random initialization — signals will be noisy."
                )
        else:
            if self.model_path:
                logger.warning(
                    f"LSTM checkpoint not found at '{self.model_path}'. "
                    "Using random initialization — signals will be noisy."
                )
        self.model.eval()
        logger.info(f"Initialized LSTM Strategy for {self.symbol}. Waiting for {self.warmup_period} bars.")

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        LSTMs typically operate on Bars, not Ticks. 
        We will ignore ticks unless we are aggregating them into bars ourselves.
        For this MVP, we assume the system sends 'bar' events or we just pass on ticks.
        But 'on_tick' is the main entry point from main.py currently.
        """
        # If input is a trade, we might want to just update current price
        # But for LSTM we really need completed bars.
        # Let's mock bar generation or see if we receive bars.
        # The current main.py only sends 'trade' events.
        # We will aggregate trades into 1-minute bars ideally, 
        # but for simplicity let's treat every 10 ticks as a "bar" to speed up testing?
        # OR: We just append the tick price as a "close" to our buffer for rolling prediction.
        
        price = float(tick["price"])
        self.prices.append(price)
        
        # Build a mock DataFrame from recent prices to calculate indicators
        if len(self.prices) < self.warmup_period:
            return None

        # Create DataFrame
        # columns=['open', 'high', 'low', 'close', 'volume']
        # We clone the price for O/H/L/C for simplicity of tick-based simulation
        df = pd.DataFrame({
            "open": list(self.prices),
            "high": list(self.prices),
            "low": list(self.prices),
            "close": list(self.prices),
            "volume": [1000] * len(self.prices) # Dummy volume
        })
        
        # Feature Engineering
        df = self.fe.calculate_features(df)
        
        # Drop NaNs
        df.dropna(inplace=True)
        
        if len(df) < self.lookback:
            return None

        # Prepare Tensor [1, seq_len, input_size]
        # Features used in LSTMModel input_size=14.
        # We need to ensure we select exactly 14 features or adjust model.
        # FeatureEngineer returns: open, high, low, close, volume, RSI, MACD..., BBU...
        # Let's select numeric columns.
        cols = ['open', 'high', 'low', 'close', 'volume', 'RSI', 'MACD', 'MACD_line', 'MACD_signal', 'log_ret', 'ATR', 'BBU', 'BBL', 'BBM']
        # Check if we have all columns
        available_cols = [c for c in cols if c in df.columns]

        if len(available_cols) < 14:
            logger.warning(
                f"LSTM [{self.symbol}]: expected 14 features, got {len(available_cols)} "
                f"(missing: {set(cols) - set(available_cols)}). Skipping signal."
            )
            return None

        recent_data = df[available_cols].iloc[-self.lookback:].values
        
        # Normalize (Standard Scaling - critical for DL)
        # Mock scaling: (x - mean) / std over the window
        mean = np.mean(recent_data, axis=0)
        std = np.std(recent_data, axis=0) + 1e-8
        scaled_data = (recent_data - mean) / std
        
        tensor_in = torch.FloatTensor(scaled_data).unsqueeze(0).to(self.device) # [1, 60, 14]
        
        # Inference
        with torch.no_grad():
            prediction = self.model(tensor_in).item() # Probability 0..1
            
        logger.debug(f"LSTM Prediction: {prediction:.4f}")
        
        signal = None
        confidence = prediction
        
        if prediction > 0.7:
            signal = "BUY"
        elif prediction < 0.3:
            signal = "SELL"
            confidence = 1.0 - prediction
            
        if signal:
            return {
                "model_id": self.model_id,
                "model_name": "LSTM_Attention_v1",
                "symbol": self.symbol,
                "signal": signal,
                "confidence": round(confidence, 2),
                "price": price,
                "timestamp": tick.get("timestamp"),
                "explanation": [f"LSTM_Prob: {prediction:.2f}"] # Simple explanation
            }
            
        return None

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None
