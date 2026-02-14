import sys
import os
import asyncio
import numpy as np
import pandas as pd
import torch

# Add current directory to sys.path
sys.path.append(os.getcwd())

from feature_engineering import FeatureEngineer
from model import load_model, HybridModel
from explainability import XAIEngine

def test_signal_pipeline():
    print("Testing Signal Engine Pipeline...")
    
    # 1. Mock Data Generation
    print("[1] Generating Mock Data...")
    dates = pd.date_range(start="2023-01-01", periods=200, freq="1min")
    data = []
    price = 100.0
    for d in dates:
        price += np.random.randn()
        data.append({
            "timestamp": d,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price + 0.1,
            "volume": 1000 + np.random.randint(0, 500)
        })
    
    # 2. Feature Engineering
    print("[2] Testing Feature Engineering...")
    fe = FeatureEngineer(window_size=60)
    input_tensor_np = fe.prepare_batch(data)
    
    if input_tensor_np is None:
        print("❌ Feature Engineering failed to produce tensor.")
        return
    
    print(f"✅ Input Tensor Shape: {input_tensor_np.shape} (Expected: (1, 60, 8))")
    
    if input_tensor_np.shape != (1, 60, 8):
        print(f"❌ Feature shape mismatch. Expected (1, 60, 8), got {input_tensor_np.shape}")
        # Identify which is wrong
        # If indicators failed, shape might be smaller
        return

    # 3. Model Inference
    print("[3] Testing Model Inference...")
    input_tensor = torch.from_numpy(input_tensor_np).float()
    model = load_model(input_dim=8)
    
    with torch.no_grad():
        logits = model(input_tensor)
        probs = logits.numpy()
        
    print(f"✅ Model Output Probs: {probs}")
    if probs.shape != (1, 3):
        print(f"❌ Model output shape mismatch. Expected (1, 3), got {probs.shape}")
        return

    # 4. Explainability (XAI)
    print("[4] Testing XAI Engine...")
    # Create background data (random for test)
    background = np.zeros((5, 60, 8))
    xai = XAIEngine(model, background)
    
    try:
        explanation = xai.explain_prediction(input_tensor)
        # Check shape of shap values
        # shap_values is list of arrays, one per class
        print(f"✅ XAI Explanation generated. Type: {type(explanation)}")
        
        if isinstance(explanation, list):
             print(f"✅ XAI Classes Explained: {len(explanation)}")
             print(f"✅ SHAP Shape per class: {explanation[0].shape}")
        else:
             print(f"✅ SHAP Shape: {explanation.shape}")

        feat_names = ['log_ret', 'rsi', 'atr', 'MACD', 'MACDh', 'MACDs', 'BBU', 'BBL']
        top_feats = xai.get_top_features(explanation, feat_names, class_idx=0)
        print(f"✅ Top Features for Class 0: {top_feats}")
        
    except Exception as e:
        print(f"❌ XAI Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_signal_pipeline()
