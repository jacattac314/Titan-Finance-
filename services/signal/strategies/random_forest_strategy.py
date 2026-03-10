import logging
from collections import deque
from typing import Any, Deque, Dict, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from feature_engineering import FeatureEngineer
from .base import Strategy, _to_epoch_ms

logger = logging.getLogger("TitanRandomForest")


class RandomForestStrategy(Strategy):
    """Adaptive random forest classifier over rolling market features."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fe = FeatureEngineer()
        self.bars: Deque[Dict[str, float]] = deque(maxlen=config.get("buffer_size", 320))
        self.min_bars = config.get("min_bars", 100)
        self.confidence_threshold = float(config.get("confidence_threshold", 0.62))
        self.retrain_every = int(config.get("retrain_every", 25))
        self._ticks_since_train = 0
        self.model_ready = False

        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=5,
            random_state=42,
            class_weight="balanced_subsample",
        )

    def _fit_model(self) -> None:
        df = pd.DataFrame(list(self.bars))
        feats = self.fe.calculate_features(df)
        if len(feats) < 50:
            return

        feats = feats.copy()
        feats["target"] = (feats["close"].shift(-1) > feats["close"]).astype(int)
        feats.dropna(inplace=True)
        if feats["target"].nunique() < 2:
            return

        feature_cols = ["RSI", "MACD", "MACD_line", "MACD_signal", "log_ret", "ATR", "BBU", "BBL", "BBM"]
        X = feats[feature_cols].to_numpy()
        y = feats["target"].to_numpy()
        self.model.fit(X, y)
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
        feature_cols = ["RSI", "MACD", "MACD_line", "MACD_signal", "log_ret", "ATR", "BBU", "BBL", "BBM"]
        prob_up = float(self.model.predict_proba(last[feature_cols].to_numpy())[0][1])

        if prob_up > self.confidence_threshold:
            signal = "BUY"
            confidence = prob_up
        elif prob_up < (1 - self.confidence_threshold):
            signal = "SELL"
            confidence = 1 - prob_up
        else:
            return None

        fi = self.model.feature_importances_
        names = np.array(feature_cols)
        top_idx = np.argsort(fi)[-3:][::-1]
        explanation = [f"{names[i]} importance: {fi[i]:.2f}" for i in top_idx]

        atr = float(last["ATR"].iloc[0]) if "ATR" in last.columns else price * 0.005
        direction = 1 if signal == "BUY" else -1

        return {
            "model_id": self.model_id,
            "model_name": "RandomForestPulse_v1",
            "symbol": self.symbol,
            "signal": signal,
            "confidence": round(confidence, 2),
            "price": price,
            "timestamp": tick.get("timestamp"),
            "forecast_price": round(price + direction * atr * confidence * 1.8, 2),
            "forecast_timestamp": _to_epoch_ms(tick.get("timestamp", 0)) + 60 * 60 * 1000,
            "explanation": explanation,
        }

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None
