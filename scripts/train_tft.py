import os
import argparse
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
import sys

# Ensure local imports work
sys.path.append(os.path.join(os.path.dirname(__file__), '../services/signal'))
from feature_engineering import FeatureEngineer
from models.tft_model import TFTModel

def train_tft(data_file: str, model_out: str):
    """
    Trains the Temporal Fusion Transformer on historical CSV data.
    """
    print(f"Loading historical data from {data_file}")
    if not os.path.exists(data_file):
        raise FileNotFoundError(f"Data file {data_file} not found. Did you run the downloader?")
        
    df = pd.read_csv(data_file)
    
    if 'close' not in df.columns:
        raise ValueError("CSV must contain 'close' column.")
        
    print("Applying Feature Engineering...")
    fe = FeatureEngineer()
    X = fe.calculate_features(df)
    
    if X.empty:
        raise ValueError("Feature engineering produced an empty dataframe.")
        
    # Desired features for TFT (Matches the expected 14 from TFTStrategy)
    cols = ['open', 'high', 'low', 'close', 'volume', 'RSI', 'MACD', 'MACD_line', 'MACD_signal', 'log_ret', 'ATR', 'BBU', 'BBL', 'BBM']
    available_cols = [c for c in cols if c in X.columns]
    
    if len(available_cols) != len(cols):
        print(f"Warning: Expected {len(cols)} columns, but only found {len(available_cols)} in dataframe.")

    data = X[available_cols].values
    
    # TFT expects a sequence (lookback) of data to predict the future (horizon).
    lookback = 60
    horizon = 5
    
    # Scale entire dataset using simple standardization for the offline run
    mean = np.mean(data, axis=0)
    std = np.std(data, axis=0) + 1e-8
    scaled_data = (data - mean) / std
    
    print(f"Constructing sequences of {lookback} bars...")
    
    X_seqs = []
    y_seqs = []
    
    # We want to predict the relative *close* price `horizon` steps into the future.
    close_idx = available_cols.index('close')
    
    for i in range(len(scaled_data) - lookback - horizon):
        X_seqs.append(scaled_data[i : i + lookback])
        # Predict the scaled close price for the next 5 steps
        y_seqs.append(scaled_data[i + lookback : i + lookback + horizon, close_idx])
        
    X_tensor = torch.FloatTensor(np.array(X_seqs))
    y_tensor = torch.FloatTensor(np.array(y_seqs))
    
    print(f"Dataset Shape - X: {X_tensor.shape}, Y: {y_tensor.shape}")
    
    split_idx = int(len(X_tensor) * 0.8)
    
    train_dataset = TensorDataset(X_tensor[:split_idx], y_tensor[:split_idx])
    val_dataset = TensorDataset(X_tensor[split_idx:], y_tensor[split_idx:])
    
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Training on device: {device}")
    
    # Initialize Model
    # Input size is len(available_cols), which is expected to be 14
    model = TFTModel(input_size=len(available_cols), d_model=64, num_layers=2, output_horizon=horizon).to(device)
    
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    
    epochs = 10
    
    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)
            
            optimizer.zero_grad()
            predictions = model(batch_X)
            
            # Predict shape is [batch, horizon] (e.g. [64, 5])
            # y shape is [batch, horizon] (e.g. [64, 5])
            loss = criterion(predictions, batch_y)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item() * batch_X.size(0)
            
        train_loss /= len(train_loader.dataset)
        
        # Validation
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X, batch_y = batch_X.to(device), batch_y.to(device)
                predictions = model(batch_X)
                loss = criterion(predictions, batch_y)
                val_loss += loss.item() * batch_X.size(0)
        
        val_loss /= len(val_loader.dataset)
        print(f"Epoch {epoch+1}/{epochs} - Train Loss: {train_loss:.4f} - Val Loss: {val_loss:.4f}")

    os.makedirs(os.path.dirname(model_out), exist_ok=True)
    torch.save(model.state_dict(), model_out)
    print(f"\nTFT Weights successfully saved to {model_out}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train TFT on historical data.")
    parser.add_argument("--data", type=str, default="data/historical/QQQ_1Min_2Y.csv", help="Path to historical CSV")
    parser.add_argument("--out", type=str, default="services/signal/models/weights/tft_weights.pth", help="Output model weights file")
    
    args = parser.parse_args()
    train_tft(args.data, args.out)
