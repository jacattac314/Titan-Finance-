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

        # 6. Bollinger Band derived: width (volatility regime) and position (mean-reversion signal)
        bb_range = df['BBU'] - df['BBL']
        df['BB_Width'] = bb_range / (df['BBM'] + 1e-8)
        df['BB_Pos'] = (df['close'] - df['BBL']) / (bb_range + 1e-8)

        # 7. Stochastic Oscillator %K and %D (14, 3)
        stoch = ta.momentum.StochasticOscillator(
            high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3
        )
        df['Stoch_K'] = stoch.stoch()
        df['Stoch_D'] = stoch.stoch_signal()

        # 8. Williams %R (14) — overbought/oversold complement to Stochastic
        df['Williams_R'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)

        # 9. Rate of Change (10) — raw momentum
        df['ROC'] = ta.momentum.roc(df['close'], window=10)

        # 10. On Balance Volume — cumulative volume-price trend
        df['OBV'] = ta.volume.on_balance_volume(df['close'], df['volume'])

        # 11. Volume Ratio — detects unusual activity relative to recent average
        df['Volume_Ratio'] = df['volume'] / (df['volume'].rolling(20).mean() + 1e-8)

        # Drop NaN (caused by lookback windows)
        df.dropna(inplace=True)

        return df
