import pandas as pd
import ta

class FeatureEngineer:
    """
    Computes technical indicators and features for ML models using 'ta' library.
    """
    def __init__(self):
        pass

    def calculate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Adds technical indicators to the DataFrame.
        Expected input columns: ['open', 'high', 'low', 'close', 'volume']
        """
        if df.empty:
            return df
            
        df = df.copy()
        
        # Ensure numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        # 1. RSI (14)
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        
        # 2. MACD (12, 26, 9)
        # ta returns Series, need to merge manually or use add_all_ta_features (too heavy)
        df['MACD'] = ta.trend.macd_diff(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['MACD_line'] = ta.trend.macd(df['close'], window_slow=26, window_fast=12)
        df['MACD_signal'] = ta.trend.macd_signal(df['close'], window_slow=26, window_fast=12, window_sign=9)

        # 3. Log Returns
        df['log_ret'] = df['close'].pct_change()
        
        # 4. Volatility (ATR 14)
        df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        
        # 5. Bollinger Bands (20, 2)
        indicator_bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
        df['BBU'] = indicator_bb.bollinger_hband()
        df['BBL'] = indicator_bb.bollinger_lband()
        df['BBM'] = indicator_bb.bollinger_mavg()

        # Drop NaN (caused by lookback windows)
        df.dropna(inplace=True)
        
        return df
