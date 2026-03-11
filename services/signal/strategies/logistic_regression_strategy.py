import logging
from collections import deque
from typing import Any, Deque, Dict, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from feature_engineering import FeatureEngineer
from .base import Strategy

logger = logging.getLogger("TitanLogisticRegression")

# Expected feature columns that must be present for LogisticRegression inference.
_REQUIRED_FEATURES = [
    "RSI",
    "MACD",
    "MACD_line",
    "MACD_signal",
    "log_ret",
    "ATR",
    "BBU",
    "BBL",
    "BBM",
]


class LogisticRegressionStrategy(Strategy):
    """Online-ish logistic regression using technical features for directional classification."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fe = FeatureEngineer()
        self.bars: Deque[Dict[str, float]] = deque(maxlen=config.get("buffer_size", 260))
        self.min_bars = config.get("min_bars", 80)
        self.confidence_threshold = float(config.get("confidence_threshold", 0.58))
        self.retrain_every = int(config.get("retrain_every", 20))
        self._ticks_since_train = 0

        self.model = LogisticRegression(max_iter=400, class_weight="balanced")
        self.scaler = StandardScaler()
        self.model_ready = False

    def _fit_model(self) -> None:
        df = pd.DataFrame(list(self.bars))
        feats = self.fe.calculate_features(df)
        if len(feats) < 40:
            return

        feats = feats.copy()
        feats["target"] = (feats["close"].shift(-1) > feats["close"]).astype(int)
        feats.dropna(inplace=True)
        if feats["target"].nunique() < 2:
            return

        feature_cols = _REQUIRED_FEATURES
        X = feats[feature_cols].to_numpy()
        y = feats["target"].to_numpy()

        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.model_ready = True

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        price = float(tick.get("price", 0.0))
        if price <= 0:
            return None

        self.bars.append({"open": price, "high": price, "low": price, "close": price, "volume": 100})
        if len(self.bars) < self.min_bars:
            return None

        self._ticks_since_train += 1
        if not self.model_ready or self._ticks_since_train >= self.retrain_every:
            self._fit_model()
            self._ticks_since_train = 0

        if not self.model_ready:
            return None

        features_df = self.fe.calculate_features(pd.DataFrame(list(self.bars)))
        if features_df.empty:
            return None

        last = features_df.iloc[[-1]]
        missing = [c for c in _REQUIRED_FEATURES if c not in features_df.columns]
        if missing:
            logger.error(
                "Feature validation failed for %s: missing columns %s.",
                self.symbol, missing,
            )
            return None
        feature_cols = _REQUIRED_FEATURES
        X_last = self.scaler.transform(last[feature_cols].to_numpy())
        prob_up = float(self.model.predict_proba(X_last)[0][1])

        if prob_up > self.confidence_threshold:
            signal = "BUY"
            confidence = prob_up
        elif prob_up < (1 - self.confidence_threshold):
            signal = "SELL"
            confidence = 1 - prob_up
        else:
            return None

        atr = float(last["ATR"].iloc[0]) if "ATR" in last.columns else price * 0.005
        direction = 1 if signal == "BUY" else -1
        forecast_price = round(price + direction * atr * confidence * 1.6, 2)

        return {
            "model_id": self.model_id,
            "model_name": "LogisticRegime_v1",
            "symbol": self.symbol,
            "signal": signal,
            "confidence": round(confidence, 2),
            "price": price,
            "timestamp": tick.get("timestamp"),
            "forecast_price": forecast_price,
            "forecast_timestamp": int(tick.get("timestamp", 0)) + 60 * 60 * 1000,
            "explanation": [
                f"ProbUp: {prob_up:.2f}",
                f"RSI: {float(last['RSI'].iloc[0]):.1f}",
                f"MACD: {float(last['MACD'].iloc[0]):.4f}",
            ],
        }

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None
