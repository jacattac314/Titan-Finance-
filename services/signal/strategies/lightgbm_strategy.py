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
        # Rolling window for feature calculation (need ~50 bars for indicators)
        self.bars = deque(maxlen=200)
        self.min_bars = 60  # Min bars needed to calc features

        # Hyperparams
        self.confidence_threshold = config.get("confidence_threshold", 0.6)

        # Model path from env (empty string = no checkpoint)
        self.model_path = config.get("model_path") or os.getenv("LIGHTGBM_MODEL_PATH", "")

        if self.model_path and os.path.isfile(self.model_path):
            self._load_model(self.model_path)
        else:
            if self.model_path:
                logger.warning(
                    f"LightGBM checkpoint not found at '{self.model_path}'. "
                    "Falling back to synthetic training — signals will be noisy."
                )
            self._train_mock_model()

    def _load_model(self, path: str):
        """Load a previously saved LightGBM booster from disk."""
        try:
            self.model = lgb.Booster(model_file=path)
            self.explainer = shap.TreeExplainer(self.model)
            logger.info(f"LightGBM model loaded from '{path}'.")
        except Exception as exc:
            logger.error(f"Failed to load LightGBM model from '{path}': {exc}. Training synthetic fallback.")
            self._train_mock_model()

    def _train_mock_model(self):
        """
        Trains a quick model on synthetic data to ensure mechanics work.
        Saves the trained model to model_path if configured.
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

        # Persist so next startup skips synthetic training
        if self.model_path:
            try:
                os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
                self.model.save_model(self.model_path)
                logger.info(f"LightGBM model saved to '{self.model_path}'.")
            except Exception as exc:
                logger.warning(f"Could not save LightGBM model: {exc}")

        # Initialize Explainer — TreeExplainer is optimized for trees
        self.explainer = shap.TreeExplainer(self.model)
        logger.info("LightGBM Model Trained & Explainer Initialized.")

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Accumulate tick data into bars? 
        # For simplicity in MVP, let's treat ticks as "close" updates 
        # OR we need a real Bar Aggregator. 
        # Let's assume the Gateway sends 'bar' events or we just use 'price' to append to a list
        # and treat every 10 ticks as a "bar" or just run on every tick with historical context.
        
        # Strict ML requires OHLCV bars.
        # If we only get ticks, we can't easily compute ATR/High/Low properly without aggregation.
        # Check if we receive 'bar' events? 
        # The Synthetic provider sends 'trade' events.
        # Let's simple-hack: aggregate ticks into 1-minute bars in memory?
        # Or just append price as close/high/low/open for that timestamp.
        
        price = float(tick.get("price", 0.0))
        if price <= 0: return None
        
        # Quick hack: Append to deque as a "bar"
        # In real world, we'd use on_bar.
        # Here we simulate a bar by treating the single tick as OHLC (all same)
        self.bars.append({
            'open': price, 'high': price, 'low': price, 'close': price, 'volume': 100
        })
        
        if len(self.bars) < self.min_bars:
            return None
            
        # Convert to DF
        df = pd.DataFrame(list(self.bars))
        
        # Calc Features
        features_df = self.fe.calculate_features(df)
        if features_df.empty:
            return None
            
        # Get last row for inference
        last_row = features_df.iloc[[-1]] 
        
        # Predict
        prob = self.model.predict(last_row)[0] # Probability of Class 1 (UP)
        
        signal = None
        if prob > self.confidence_threshold:
            signal = "BUY"
        elif prob < (1 - self.confidence_threshold):
            signal = "SELL"
            
        if signal:
            # Explain
            shap_values = self.explainer.shap_values(last_row)
            # shap_values is list of arrays for binary? or array?
            # For binary, it might be array.
            # Shap 0.40+ returns Explanation object or values. TreeExplainer usually returns matrix.
            
            # Simple top feature extraction
            # shap_values[1] is usually positive class contribution
            if isinstance(shap_values, list):
                vals = shap_values[1][0]
            else:
                vals = shap_values[0]
                
            # Get top 3 features
            feature_names = last_row.columns.tolist()
            # Sort by absolute impact
            top_indices = np.argsort(np.abs(vals))[-3:][::-1]
            explanation = [
                f"{feature_names[i]}: {vals[i]:.4f}" for i in top_indices
            ]
            
            return {
                "model_id": self.model_id,
                "model_name": "LightGBM_v1",
                "symbol": self.symbol,
                "signal": signal,
                "confidence": round(float(prob if signal == "BUY" else 1-prob), 2),
                "price": price,
                "timestamp": tick.get("timestamp"),
                "explanation": explanation
            }
            
        return None

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # To be implemented when Gateway sends real bars
        pass
