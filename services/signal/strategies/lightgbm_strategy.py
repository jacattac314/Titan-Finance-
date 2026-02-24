import logging
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
        # Rolling window for feature calculation (need ~50 bars for indicators)
        self.bars = deque(maxlen=200) 
        self.min_bars = 60 # Min bars needed to calc features
        
        # Hyperparams
        self.confidence_threshold = config.get("confidence_threshold", 0.6)
        
        # Train on startup? For MVP, yes.
        # In prod, load saved model.
        self._train_mock_model()

    def _train_mock_model(self):
        """
        Trains a quick model on synthetic data to ensure mechanics work.
        """
        logger.info("Training initial LightGBM model on synthetic data...")
        # Generate dummy data
        data = {
            'open': np.random.rand(1000) * 100,
            'high': np.random.rand(1000) * 100,
            'low': np.random.rand(1000) * 100,
            'close': np.random.rand(1000) * 100,
            'volume': np.random.rand(1000) * 1000
        }
        df = pd.DataFrame(data)
        
        # Features
        X = self.fe.calculate_features(df)
        if X.empty:
            logger.warning("Feature engineering returned empty DF.")
            return

        # Target: 1 if next return > 0, else 0
        y = (X['close'].shift(-1) > X['close']).astype(int)
        
        # Align X and y
        X = X.iloc[:-1]
        y = y.iloc[:-1]
        
        # Train
        train_data = lgb.Dataset(X, label=y)
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'verbosity': -1,
            'boosting_type': 'gbdt'
        }
        self.model = lgb.train(params, train_data, num_boost_round=50)
        
        # Initialize Explainer
        # TreeExplainer is optimized for trees
        self.explainer = shap.TreeExplainer(self.model)
        logger.info("LightGBM Model Trained & Explainer Initialized.")

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        price = float(tick.get("price", 0.0))
        if price <= 0:
            return None
        # Treat single tick as a flat OHLCV bar (tick-level simulation)
        self.bars.append({
            'open': price, 'high': price, 'low': price, 'close': price, 'volume': 100
        })
        return self._infer(price=price, timestamp=tick.get("timestamp"))

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a completed OHLCV bar from the Gateway."""
        self.bars.append({
            'open': float(bar.get('open', 0.0)),
            'high': float(bar.get('high', 0.0)),
            'low': float(bar.get('low', 0.0)),
            'close': float(bar.get('close', 0.0)),
            'volume': float(bar.get('volume', 100)),
        })
        return self._infer(price=float(bar.get('close', 0.0)), timestamp=bar.get("timestamp"))

    def _infer(self, price: float, timestamp) -> Optional[Dict[str, Any]]:
        """Run LightGBM inference on the current bar buffer."""
        if len(self.bars) < self.min_bars:
            return None

        df = pd.DataFrame(list(self.bars))
        features_df = self.fe.calculate_features(df)
        if features_df.empty:
            return None

        last_row = features_df.iloc[[-1]]
        prob = self.model.predict(last_row)[0]

        signal = None
        if prob > self.confidence_threshold:
            signal = "BUY"
        elif prob < (1 - self.confidence_threshold):
            signal = "SELL"

        if not signal:
            return None

        shap_values = self.explainer.shap_values(last_row)
        if isinstance(shap_values, list):
            vals = shap_values[1][0]
        else:
            vals = shap_values[0]

        feature_names = last_row.columns.tolist()
        top_indices = np.argsort(np.abs(vals))[-3:][::-1]
        explanation = [f"{feature_names[i]}: {vals[i]:.4f}" for i in top_indices]

        return {
            "model_id": self.model_id,
            "model_name": "LightGBM_v1",
            "symbol": self.symbol,
            "signal": signal,
            "confidence": round(float(prob if signal == "BUY" else 1 - prob), 2),
            "price": price,
            "timestamp": timestamp,
            "explanation": explanation
        }
