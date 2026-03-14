import logging
import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import shap
from typing import Dict, Any, Optional, Deque
from collections import deque
from .base import Strategy
from feature_engineering import FeatureEngineer

logger = logging.getLogger("TitanLightGBM")

class LightGBMStrategy(Strategy):
    """
    ML Strategy using LightGBM for classification (Up/Down).
    Includes SHAP explainability.
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fe = FeatureEngineer()
        self.model = None
        self.explainer = None
        self._disabled = False
        # Rolling window for feature calculation (need ~50 bars for indicators)
        self.bars = deque(maxlen=200)
        self.min_bars = 60  # Min bars needed to calc features

        # Hyperparams
        self.confidence_threshold = config.get("confidence_threshold", 0.6)

        self.model_path = os.path.join(os.path.dirname(__file__), '../models/weights/lightgbm_model.txt')
        self._load_model()

    def _load_model(self):
        """
        Loads the pre-trained LightGBM model from disk.

        If the weights file is absent the strategy is marked as disabled so
        that on_tick() returns None immediately without raising.  This allows
        the service to start and warm up during CI or before training completes,
        while making the degraded state fully visible in logs.
        """
        if not os.path.exists(self.model_path):
            logger.error(
                "LightGBM model weights not found at '%s'. "
                "Run train_lgbm.py to generate them. "
                "Strategy will be disabled until weights are present.",
                self.model_path,
            )
            self.model = None
            self._disabled = True
            return

        logger.info("Loading LightGBM model from %s...", self.model_path)
        self.model = lgb.Booster(model_file=self.model_path)

        # Initialize Explainer
        self.explainer = shap.TreeExplainer(self.model)
        self._disabled = False
        logger.info("LightGBM model loaded & SHAP explainer initialised.")

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Return immediately if model weights were never loaded.
        if self._disabled or self.model is None:
            return None

        price = float(tick.get("price", 0.0))
        if price <= 0:
            return None

        # Append tick as a synthetic bar (OHLC all equal) for feature calculation.
        # A proper bar aggregator should replace this in production.
        self.bars.append({
            'open': price, 'high': price, 'low': price, 'close': price, 'volume': 100
        })

        if len(self.bars) < self.min_bars:
            return None

        # Convert to DF and calculate features
        df = pd.DataFrame(list(self.bars))
        features_df = self.fe.calculate_features(df)
        if features_df.empty:
            return None

        last_row = features_df.iloc[[-1]]

        # Run inference; catch runtime errors so one bad tick doesn't crash the loop.
        try:
            prob = self.model.predict(last_row)[0]  # Probability of Class 1 (UP)
        except Exception as exc:
            logger.error("LightGBM inference failed for %s: %s", self.symbol, exc)
            return None

        signal = None
        if prob > self.confidence_threshold:
            signal = "BUY"
        elif prob < (1 - self.confidence_threshold):
            signal = "SELL"

        if signal:
            # SHAP explanation
            try:
                shap_values = self.explainer.shap_values(last_row)
                if isinstance(shap_values, list):
                    vals = shap_values[1][0]
                else:
                    vals = shap_values[0]
                feature_names = last_row.columns.tolist()
                top_indices = np.argsort(np.abs(vals))[-3:][::-1]
                explanation = [
                    f"{feature_names[i]}: {vals[i]:.4f}" for i in top_indices
                ]
            except Exception as exc:
                logger.warning("SHAP explanation failed for %s: %s", self.symbol, exc)
                explanation = []

            # 1-hour forecast: project price using ATR and confidence
            atr = float(last_row['ATR'].iloc[0]) if 'ATR' in last_row.columns else price * 0.005
            conf = float(prob if signal == "BUY" else 1 - prob)
            direction = 1.0 if signal == "BUY" else -1.0
            forecast_price = round(price + direction * atr * conf * 2.0, 2)

            current_ts = tick.get("timestamp", 0)
            forecast_timestamp = int(current_ts) + (60 * 60 * 1000)  # +1 hour in ms

            return {
                "model_id": self.model_id,
                "model_name": "LightGBM_v1",
                "symbol": self.symbol,
                "signal": signal,
                "confidence": round(conf, 2),
                "price": price,
                "timestamp": current_ts,
                "explanation": explanation,
                "forecast_price": forecast_price,
                "forecast_timestamp": forecast_timestamp
            }

        return None

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a real OHLCV bar from the Gateway."""
        if self._disabled or self.model is None:
            return None

        close = float(bar.get("close", 0.0))
        if close <= 0:
            return None

        self.bars.append({
            "open": float(bar.get("open", close)),
            "high": float(bar.get("high", close)),
            "low": float(bar.get("low", close)),
            "close": close,
            "volume": float(bar.get("volume", 0)),
        })

        if len(self.bars) < self.min_bars:
            return None

        df = pd.DataFrame(list(self.bars))
        features_df = self.fe.calculate_features(df)
        if features_df.empty:
            return None

        last_row = features_df.iloc[[-1]]

        try:
            prob = self.model.predict(last_row)[0]
        except Exception as exc:
            logger.error("LightGBM inference failed for %s: %s", self.symbol, exc)
            return None

        signal = None
        if prob > self.confidence_threshold:
            signal = "BUY"
        elif prob < (1 - self.confidence_threshold):
            signal = "SELL"

        if signal:
            try:
                shap_values = self.explainer.shap_values(last_row)
                if isinstance(shap_values, list):
                    vals = shap_values[1][0]
                else:
                    vals = shap_values[0]
                feature_names = last_row.columns.tolist()
                top_indices = np.argsort(np.abs(vals))[-3:][::-1]
                explanation = [
                    f"{feature_names[i]}: {vals[i]:.4f}" for i in top_indices
                ]
            except Exception as exc:
                logger.warning("SHAP explanation failed for %s: %s", self.symbol, exc)
                explanation = []

            atr = float(last_row["ATR"].iloc[0]) if "ATR" in last_row.columns else close * 0.005
            conf = float(prob if signal == "BUY" else 1 - prob)
            direction = 1.0 if signal == "BUY" else -1.0
            forecast_price = round(close + direction * atr * conf * 2.0, 2)

            current_ts = bar.get("timestamp", 0)
            forecast_timestamp = int(current_ts) + (60 * 60 * 1000)

            return {
                "model_id": self.model_id,
                "model_name": "LightGBM_v1",
                "symbol": self.symbol,
                "signal": signal,
                "confidence": round(conf, 2),
                "price": close,
                "timestamp": current_ts,
                "explanation": explanation,
                "forecast_price": forecast_price,
                "forecast_timestamp": forecast_timestamp,
            }

        return None
