"""
Train LightGBM directional classifier on historical OHLCV data.

Improvements over the original script:
  • TimeSeriesSplit (5-fold) cross-validation for realistic out-of-sample
    performance estimation on time series data (no data leakage).
  • Stronger regularisation: L1/L2 penalties, min_child_samples, bagging.
  • Early stopping on a held-out validation set to prevent over-fitting.
  • Model card saved as JSON alongside the model weights for MLOps traceability.

Usage:
    python scripts/train_lgbm.py --data data/historical/SPY_1Min_2Y.csv
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

sys.path.append(os.path.join(os.path.dirname(__file__), "../services/signal"))
from feature_engineering import FeatureEngineer  # noqa: E402

# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------
PARAMS = {
    "objective": "binary",
    "metric": ["binary_logloss", "auc"],
    "boosting_type": "gbdt",
    "learning_rate": 0.03,
    "num_leaves": 63,
    "max_depth": 6,
    "min_child_samples": 20,      # Minimum data in leaf — avoids over-fitting
    "feature_fraction": 0.7,      # Column subsampling per tree
    "bagging_fraction": 0.8,      # Row subsampling
    "bagging_freq": 5,
    "lambda_l1": 0.1,             # L1 regularisation
    "lambda_l2": 0.1,             # L2 regularisation
    "verbose": -1,
}

TARGET_HORIZON = 5    # Predict if close[t+5] > close[t]
N_BOOST_ROUNDS = 1000
EARLY_STOPPING = 50   # Stop if validation metric doesn't improve for 50 rounds
CV_FOLDS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_dataset(data_file: str) -> tuple[pd.DataFrame, pd.Series]:
    print(f"Loading data from {data_file}")
    df = pd.read_csv(data_file)
    if "close" not in df.columns:
        raise ValueError("CSV must contain a 'close' column.")

    print("Applying feature engineering...")
    fe = FeatureEngineer()
    X = fe.calculate_features(df)
    if X.empty:
        raise ValueError("Feature engineering produced an empty dataframe.")

    print(f"Features ({len(X.columns)}): {X.columns.tolist()}")

    # Binary target: 1 if price is higher TARGET_HORIZON bars from now
    future_close = X["close"].shift(-TARGET_HORIZON)
    y = (future_close > X["close"]).astype(int)

    X = X.iloc[:-TARGET_HORIZON]
    y = y.iloc[:-TARGET_HORIZON]

    print(f"Dataset: {len(X)} rows | class balance: {y.mean():.1%} UP")
    return X, y


def cross_validate(X: pd.DataFrame, y: pd.Series) -> dict:
    """Walk-forward cross-validation to estimate generalisation performance."""
    tscv = TimeSeriesSplit(n_splits=CV_FOLDS)
    fold_auc, fold_acc = [], []

    print(f"\nRunning {CV_FOLDS}-fold TimeSeriesSplit cross-validation...")
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X), 1):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        dtrain = lgb.Dataset(X_tr, label=y_tr)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)

        model = lgb.train(
            PARAMS,
            dtrain,
            num_boost_round=N_BOOST_ROUNDS,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)],
        )

        probs = model.predict(X_val)
        preds = (probs > 0.5).astype(int)
        auc = roc_auc_score(y_val, probs)
        acc = accuracy_score(y_val, preds)
        fold_auc.append(auc)
        fold_acc.append(acc)
        print(f"  Fold {fold}/{CV_FOLDS}  AUC={auc:.4f}  Acc={acc:.4f}"
              f"  best_iter={model.best_iteration}")

    cv_results = {
        "mean_auc": float(np.mean(fold_auc)),
        "std_auc": float(np.std(fold_auc)),
        "mean_acc": float(np.mean(fold_acc)),
        "std_acc": float(np.std(fold_acc)),
    }
    print(f"\nCV results: AUC={cv_results['mean_auc']:.4f}±{cv_results['std_auc']:.4f}"
          f"  Acc={cv_results['mean_acc']:.4f}±{cv_results['std_acc']:.4f}")
    return cv_results


def train_final(X: pd.DataFrame, y: pd.Series) -> tuple[lgb.Booster, dict]:
    """Train final model on 80% of data, validate on last 20%."""
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    dtrain = lgb.Dataset(X_train, label=y_train)
    dtest = lgb.Dataset(X_test, label=y_test, reference=dtrain)

    print(f"\nTraining final model: {len(X_train)} train / {len(X_test)} test rows")
    model = lgb.train(
        PARAMS,
        dtrain,
        num_boost_round=N_BOOST_ROUNDS,
        valid_sets=[dtrain, dtest],
        valid_names=["train", "test"],
        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=True)],
    )

    probs = model.predict(X_test)
    preds = (probs > 0.5).astype(int)
    test_metrics = {
        "test_auc": float(roc_auc_score(y_test, probs)),
        "test_acc": float(accuracy_score(y_test, preds)),
        "best_iteration": model.best_iteration,
    }
    print(f"Final model — AUC={test_metrics['test_auc']:.4f}  Acc={test_metrics['test_acc']:.4f}")

    # Feature importances (top 10)
    importances = dict(
        sorted(
            zip(X.columns.tolist(), model.feature_importance(importance_type="gain")),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
    )
    test_metrics["top_features"] = {k: float(v) for k, v in importances.items()}

    return model, test_metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def train_lgbm(data_file: str, model_out: str, skip_cv: bool = False):
    X, y = build_dataset(data_file)

    cv_results: dict = {}
    if not skip_cv:
        cv_results = cross_validate(X, y)

    model, test_metrics = train_final(X, y)

    os.makedirs(os.path.dirname(model_out), exist_ok=True)
    model.save_model(model_out)
    print(f"\nModel saved to {model_out}")

    # Save model card alongside weights
    model_card = {
        "model_id": "lgb_spy_v1",
        "model_type": "LightGBM binary classifier",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_file": data_file,
        "target_horizon_bars": TARGET_HORIZON,
        "n_features": len(X.columns),
        "feature_names": X.columns.tolist(),
        "hyperparameters": PARAMS,
        "cv": cv_results,
        **test_metrics,
    }
    card_path = model_out.replace(".txt", "_card.json")
    with open(card_path, "w") as f:
        json.dump(model_card, f, indent=2)
    print(f"Model card saved to {card_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LightGBM on historical OHLCV data.")
    parser.add_argument(
        "--data",
        default="data/historical/SPY_1Min_2Y.csv",
        help="Path to historical CSV",
    )
    parser.add_argument(
        "--out",
        default="services/signal/models/weights/lightgbm_model.txt",
        help="Output model file path (.txt)",
    )
    parser.add_argument(
        "--skip-cv",
        action="store_true",
        help="Skip cross-validation (faster, for quick iteration)",
    )
    args = parser.parse_args()
    train_lgbm(args.data, args.out, skip_cv=args.skip_cv)
