import os
import argparse
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import sys

# Ensure local imports work for FeatureEngineer
sys.path.append(os.path.join(os.path.dirname(__file__), '../services/signal'))
from feature_engineering import FeatureEngineer

def train_lgbm(data_file: str, model_out: str):
    """
    Trains a LightGBM model on historical CSV data.
    """
    print(f"Loading historical data from {data_file}")
    if not os.path.exists(data_file):
        raise FileNotFoundError(f"Data file {data_file} not found. Did you run the downloader?")
        
    df = pd.read_csv(data_file)
    
    # Needs to match 'timestamp', 'open', 'high', 'low', 'close', 'volume'
    # Alpaca data usually has these columns
    if 'close' not in df.columns:
        raise ValueError("CSV must contain 'close' column.")
        
    print("Applying Feature Engineering...")
    fe = FeatureEngineer()
    
    # Feature Engineer requires index to be sequential or datetime, 
    # it calculates rolling windows so we just pass the DF
    X = fe.calculate_features(df)
    
    if X.empty:
        raise ValueError("Feature engineering produced an empty dataframe (not enough rows for lookback?)")

    print(f"Features generated: {X.columns.tolist()}")

    # Define Target: 1 if the 'close' price 5 periods from now is higher than current 'close'
    # Shift(-5) pulls the future row up to the current index
    target_horizon = 5
    future_close = X['close'].shift(-target_horizon)
    
    # 1 for UP, 0 for DOWN (or flat)
    y = (future_close > X['close']).astype(int)
    
    # Drop the last 'target_horizon' rows because they don't have a future to predict
    X = X.iloc[:-target_horizon]
    y = y.iloc[:-target_horizon]
    
    # Optional: We can drop open/high/low/close/volume if we only want indicators,
    # but the current feature engineer keeps them. LightGBM handles them fine.
    
    print(f"Training dataset size: {len(X)} rows")
    
    # Split chronologically (do not shuffle time series!)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    train_data = lgb.Dataset(X_train, label=y_train)
    test_data = lgb.Dataset(X_test, label=y_test, reference=train_data)
    
    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'learning_rate': 0.05,
        'num_leaves': 31,
        'max_depth': -1,
        'feature_fraction': 0.8,
        'verbose': -1
    }
    
    print(f"Training LightGBM model on {len(X_train)} samples, validating on {len(X_test)} samples...")
    model = lgb.train(
        params,
        train_data,
        num_boost_round=500,
        valid_sets=[train_data, test_data]
    )
    
    os.makedirs(os.path.dirname(model_out), exist_ok=True)
    model.save_model(model_out)
    print(f"\nModel successfully saved to {model_out}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LightGBM on historical data.")
    parser.add_argument("--data", type=str, default="data/historical/SPY_1Min_2Y.csv", help="Path to historical CSV")
    parser.add_argument("--out", type=str, default="services/signal/models/weights/lightgbm_model.txt", help="Output model file")
    
    args = parser.parse_args()
    train_lgbm(args.data, args.out)
