"""
Unit tests for services/signal/feature_engineering.py

FeatureEngineer.calculate_features produces the input matrix for all ML
models.  Silently wrong features (values out of valid range, wrong column
presence, unexpected NaNs) produce silently wrong signals, so each
indicator's invariants are verified here.
"""
import pytest
import pandas as pd
import numpy as np
from feature_engineering import FeatureEngineer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engineer() -> FeatureEngineer:
    return FeatureEngineer()


def make_ohlcv(n: int = 100, base_price: float = 100.0) -> pd.DataFrame:
    """
    Generate a simple deterministic OHLCV DataFrame of length n.
    Prices form a gentle sine wave so that indicators have meaningful variance.
    """
    np.random.seed(0)
    close = base_price + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1.0)  # keep positive
    df = pd.DataFrame({
        "open":   close * 0.999,
        "high":   close * 1.002,
        "low":    close * 0.998,
        "close":  close,
        "volume": np.random.randint(1000, 50000, size=n).astype(float),
    })
    return df


EXPECTED_COLUMNS = {"RSI", "MACD", "MACD_line", "MACD_signal", "log_ret", "ATR", "BBU", "BBL", "BBM"}


# ---------------------------------------------------------------------------
# Empty DataFrame
# ---------------------------------------------------------------------------

class TestEmptyDataFrame:
    def test_returns_empty_df_unchanged(self):
        fe = make_engineer()
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        result = fe.calculate_features(empty)
        assert result.empty


# ---------------------------------------------------------------------------
# Output columns
# ---------------------------------------------------------------------------

class TestOutputColumns:
    def test_all_expected_feature_columns_present(self):
        fe = make_engineer()
        result = fe.calculate_features(make_ohlcv(100))
        for col in EXPECTED_COLUMNS:
            assert col in result.columns, f"Column '{col}' missing from output"

    def test_original_ohlcv_columns_preserved(self):
        fe = make_engineer()
        result = fe.calculate_features(make_ohlcv(100))
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns


# ---------------------------------------------------------------------------
# No NaN in output
# ---------------------------------------------------------------------------

class TestNoNaN:
    def test_output_contains_no_nan_values(self):
        fe = make_engineer()
        result = fe.calculate_features(make_ohlcv(100))
        nan_cols = result.columns[result.isna().any()].tolist()
        assert nan_cols == [], f"NaN values found in columns: {nan_cols}"

    def test_row_count_reduced_by_dropna(self):
        fe = make_engineer()
        df = make_ohlcv(100)
        result = fe.calculate_features(df)
        # Longest lookback is BB(20) + ATR(14), so some rows must be dropped
        assert len(result) < len(df)


# ---------------------------------------------------------------------------
# RSI bounds [0, 100]
# ---------------------------------------------------------------------------

class TestRSI:
    def test_rsi_values_within_valid_range(self):
        fe = make_engineer()
        result = fe.calculate_features(make_ohlcv(150))
        assert result["RSI"].min() >= 0.0
        assert result["RSI"].max() <= 100.0


# ---------------------------------------------------------------------------
# ATR non-negative
# ---------------------------------------------------------------------------

class TestATR:
    def test_atr_values_are_non_negative(self):
        fe = make_engineer()
        result = fe.calculate_features(make_ohlcv(150))
        assert (result["ATR"] >= 0).all()


# ---------------------------------------------------------------------------
# Bollinger Band ordering: BBU >= BBM >= BBL
# ---------------------------------------------------------------------------

class TestBollingerBands:
    def test_upper_band_above_or_equal_to_middle(self):
        fe = make_engineer()
        result = fe.calculate_features(make_ohlcv(150))
        assert (result["BBU"] >= result["BBM"]).all()

    def test_middle_band_above_or_equal_to_lower(self):
        fe = make_engineer()
        result = fe.calculate_features(make_ohlcv(150))
        assert (result["BBM"] >= result["BBL"]).all()


# ---------------------------------------------------------------------------
# Input does not mutate the original DataFrame
# ---------------------------------------------------------------------------

class TestNoMutation:
    def test_original_dataframe_unchanged(self):
        fe = make_engineer()
        df = make_ohlcv(100)
        original_cols = list(df.columns)
        original_close = df["close"].copy()
        fe.calculate_features(df)
        assert list(df.columns) == original_cols
        pd.testing.assert_series_equal(df["close"], original_close)
