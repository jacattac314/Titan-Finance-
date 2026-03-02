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
        self.min_bars = 60 # Min bars needed to calc features
        
        # Hyperparams
        self.confidence_threshold = config.get("confidence_threshold", 0.6)
        
        self.model_path = os.path.join(os.path.dirname(__file__), '../models/weights/lightgbm_model.txt')
        self._load_model()

    def _load_model(self):
        """
        Loads the pre-trained LightGBM model from disk.
        """
        if not os.path.exists(self.model_path):
            logger.warning(f"LightGBM model not found at {self.model_path}. Please run train_lgbm.py. Using mock model for now.")
            # Fallback for CI/CD or if user hasn't trained it yet
            self.model = None
            return

        logger.info(f"Loading LightGBM model from {self.model_path}...")
        self.model = lgb.Booster(model_file=self.model_path)
        
        # Initialize Explainer
        self.explainer = shap.TreeExplainer(self.model)
        logger.info("LightGBM Model loaded & Explainer Initialized from disk.")

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
        # To be implemented when Gateway sends real bars
        pass
