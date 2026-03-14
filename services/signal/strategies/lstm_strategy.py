import logging
import numpy as np
import pandas as pd
import torch
from typing import Dict, Any, Optional, Deque
from collections import deque
from .base import Strategy
from feature_engineering import FeatureEngineer
from models.lstm_model import LSTMModel

logger = logging.getLogger("TitanLSTM")

# Expected feature columns that must be present for LSTM inference.
_REQUIRED_FEATURES = [
    'open', 'high', 'low', 'close', 'volume',
    'RSI', 'MACD', 'MACD_line', 'MACD_signal',
    'log_ret', 'ATR', 'BBU', 'BBL', 'BBM',
]


class LSTMStrategy(Strategy):
    """
    Deep Learning Strategy using LSTM + Attention.
    Predicts next bar direction based on a lookback window of 60 bars.
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lookback = config.get("lookback", 60)
        self.device = torch.device("cpu")  # use cpu for inference in this container

        # Data Buffer
        # We need enough data for feature engineering + lookback
        self.warmup_period = 200
        self.prices: Deque[float] = deque(maxlen=self.warmup_period)
        self.data_buffer: Deque[Dict] = deque(maxlen=self.warmup_period)

        # Feature Engineering
        self.fe = FeatureEngineer()

        # Model
        self.model = LSTMModel(input_size=14, hidden_size=64, num_layers=2)
        self.model.eval()
        # In a real scenario, we would load weights here:
        # self.model.load_state_dict(torch.load("lstm_weights.pth"))
        logger.info(
            "Initialised LSTM Strategy for %s. Waiting for %d bars.",
            self.symbol, self.warmup_period,
        )

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        LSTMs typically operate on Bars, not Ticks.
        For this MVP we aggregate tick prices into a rolling buffer and treat
        each entry as a synthetic bar close.
        """
        price = float(tick["price"])
        self.prices.append(price)

        if len(self.prices) < self.warmup_period:
            return None

        # Build DataFrame from recent prices to calculate indicators.
        # O/H/L/C are all set to price (tick-based simulation).
        df = pd.DataFrame({
            "open":   list(self.prices),
            "high":   list(self.prices),
            "low":    list(self.prices),
            "close":  list(self.prices),
            "volume": [1000] * len(self.prices),
        })

        df = self.fe.calculate_features(df)
        df.dropna(inplace=True)

        if len(df) < self.lookback:
            return None

        # Validate that all required feature columns are present before slicing.
        missing = [c for c in _REQUIRED_FEATURES if c not in df.columns]
        if missing:
            logger.error(
                "LSTM feature validation failed for %s: missing columns %s. "
                "Check FeatureEngineer output.",
                self.symbol, missing,
            )
            return None

        recent_data = df[_REQUIRED_FEATURES].iloc[-self.lookback:].values

        # Normalize over the window (standard scaling).
        mean = np.mean(recent_data, axis=0)
        std = np.std(recent_data, axis=0) + 1e-8
        scaled_data = (recent_data - mean) / std

        tensor_in = torch.FloatTensor(scaled_data).unsqueeze(0).to(self.device)  # [1, 60, 14]

        # Inference — catch runtime errors (shape mismatch, OOM, etc.) so a bad
        # tick does not crash the entire signal loop.
        try:
            with torch.no_grad():
                prediction = self.model(tensor_in).item()  # Probability 0..1
        except RuntimeError as exc:
            logger.error(
                "LSTM inference failed for %s: %s. Input shape: %s",
                self.symbol, exc, tensor_in.shape,
            )
            return None

        logger.debug("LSTM Prediction: %.4f", prediction)

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
                "explanation": [f"LSTM_Prob: {prediction:.2f}"],
            }

        return None

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a real OHLCV bar, using proper high/low/open for richer features."""
        close = float(bar.get("close", 0.0))
        if close <= 0:
            return None

        self.data_buffer.append({
            "open":   float(bar.get("open", close)),
            "high":   float(bar.get("high", close)),
            "low":    float(bar.get("low", close)),
            "close":  close,
            "volume": float(bar.get("volume", 1000)),
        })

        if len(self.data_buffer) < self.warmup_period:
            return None

        df = pd.DataFrame(list(self.data_buffer))
        df = self.fe.calculate_features(df)
        df.dropna(inplace=True)

        if len(df) < self.lookback:
            return None

        missing = [c for c in _REQUIRED_FEATURES if c not in df.columns]
        if missing:
            logger.error(
                "LSTM bar feature validation failed for %s: missing columns %s",
                self.symbol, missing,
            )
            return None

        recent_data = df[_REQUIRED_FEATURES].iloc[-self.lookback:].values
        mean = np.mean(recent_data, axis=0)
        std = np.std(recent_data, axis=0) + 1e-8
        scaled_data = (recent_data - mean) / std

        tensor_in = torch.FloatTensor(scaled_data).unsqueeze(0).to(self.device)

        try:
            with torch.no_grad():
                prediction = self.model(tensor_in).item()
        except RuntimeError as exc:
            logger.error(
                "LSTM bar inference failed for %s: %s. Input shape: %s",
                self.symbol, exc, tensor_in.shape,
            )
            return None

        logger.debug("LSTM bar prediction: %.4f", prediction)

        signal = None
        confidence = prediction

        if prediction > 0.7:
            signal = "BUY"
        elif prediction < 0.3:
            signal = "SELL"
            confidence = 1.0 - prediction

        if signal:
            atr_col = df["ATR"].iloc[-1] if "ATR" in df.columns else close * 0.005
            direction = 1 if signal == "BUY" else -1
            return {
                "model_id": self.model_id,
                "model_name": "LSTM_Attention_v1",
                "symbol": self.symbol,
                "signal": signal,
                "confidence": round(confidence, 2),
                "price": close,
                "timestamp": bar.get("timestamp"),
                "forecast_price": round(close + direction * float(atr_col) * confidence * 2.0, 2),
                "forecast_timestamp": int(bar.get("timestamp", 0)) + 60 * 1000,
                "explanation": [f"LSTM_Prob: {prediction:.2f}"],
            }

        return None
