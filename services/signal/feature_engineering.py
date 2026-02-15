import pandas as pd
import ta
import numpy as np
import logging

logger = logging.getLogger("TitanFeatures")

class FeatureEngineer:
    def __init__(self, window_size=60):
        self.window_size = window_size

    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical indicators using 'ta' library.
        Expected columns: 'open', 'high', 'low', 'close', 'volume'
        """
        # Ensure we have enough data
        if len(df) < self.window_size:
            return df
            


        # 1. Log Returns
        df['log_ret'] = np.log(df['close'] / df['close'].shift(1))

        # 2. RSI (Relative Strength Index)
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

        # 3. MACD (Moving Average Convergence Divergence)
        macd = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['MACD_12_26_9'] = macd.macd()
        df['MACDh_12_26_9'] = macd.macd_diff()
        df['MACDs_12_26_9'] = macd.macd_signal()

        # 4. Bollinger Bands
        bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
        df['BBU_20_2.0'] = bb.bollinger_hband()
        df['BBL_20_2.0'] = bb.bollinger_lband()
        df['BBM_20_2.0'] = bb.bollinger_mavg()

        # 5. ATR (Average True Range) - Volatility
        df['atr'] = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

        # 6. Volume Osc (Simple SMA on Volume)
        df['vol_oma'] = ta.trend.SMAIndicator(close=df['volume'], window=10).sma_indicator()

        # Handle NaNs created by indicators
        df.dropna(inplace=True)
        return df

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize features using Z-Score or MinMax.
        For financial time series, rolling Z-Score is often safer to avoid lookahead bias,
        but for this window-based inference, we can standardize the window itself or use global stats.
        Here we use Z-Score normalization on the window level for simplicity in this MVP.
        """
        # Select numeric columns only
        cols_to_norm = [c for c in df.columns if c not in ['timestamp', 'symbol']]
        
        # Epsilon to avoid division by zero
        epsilon = 1e-8
        
        # Window-based normalization (standardizing the current window)
        # This preserves the shape of the movement within the window but removes absolute scale
        return (df[cols_to_norm] - df[cols_to_norm].mean()) / (df[cols_to_norm].std() + epsilon)

    def prepare_batch(self, ticks: list) -> np.ndarray:
        """
        Convert raw ticks/bars to model input tensor.
        Returns: (Batch=1, Sequence, Features)
        """
        if not ticks or len(ticks) < self.window_size + 30: # Need extra for valid indicators
            return None
            
        df = pd.DataFrame(ticks)
        
        # Ensure required columns exist
        required_cols = {'open', 'high', 'low', 'close', 'volume'}
        if not required_cols.issubset(df.columns):
            logger.error(f"Missing columns. Got: {df.columns}")
            return None

        # Add Indicators
        df = self.add_technical_indicators(df)
        
        # Drop inputs that were just for calculation if needed, or keep all
        # We'll select specific features for the model
        feature_cols = [
            'log_ret', 'rsi', 'atr', 
            'MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9',
            'BBU_20_2.0', 'BBL_20_2.0'
        ]
        
        # Check if columns exist (pandas_ta naming might vary slightly, good to be robust)
        available_cols = [c for c in feature_cols if c in df.columns]
        
        if len(available_cols) < len(feature_cols):
             logger.warning(f"Some features missing. Available: {df.columns}")
        
        df_model = df[available_cols].copy()
        
        # Take the last window_size rows
        if len(df_model) < self.window_size:
            return None
            
        df_window = df_model.iloc[-self.window_size:].copy()
        
        # Normalize
        df_norm = self.normalize(df_window)
        
        # Return as (1, Sequence, Features)
        return np.expand_dims(df_norm.values, axis=0)
