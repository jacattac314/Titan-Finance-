"""
Unit tests for services/gateway/providers/synthetic_provider.py

SyntheticDataProvider generates GBM-based tick and bar data for pipeline
testing without external API dependencies.  Tests verify the structural
contracts (OHLCV columns, price positivity, OHLC relationships) that the
rest of the pipeline relies on.
"""
import pytest
from datetime import datetime, timedelta
from providers.synthetic_provider import SyntheticDataProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_provider() -> SyntheticDataProvider:
    return SyntheticDataProvider()


def make_bars(provider=None, timeframe="1Day", days=10):
    p = provider or make_provider()
    end = datetime(2024, 6, 1)
    start = end - timedelta(days=days)
    return p.get_historical_bars("SPY", start, end, timeframe)


# ---------------------------------------------------------------------------
# get_latest_price
# ---------------------------------------------------------------------------

class TestGetLatestPrice:
    def test_returns_positive_price_for_known_symbol(self):
        p = make_provider()
        assert p.get_latest_price("SPY") > 0

    def test_returns_default_for_unknown_symbol(self):
        p = make_provider()
        assert p.get_latest_price("UNKNOWN_XYZ") == 100.0

    def test_all_builtin_symbols_have_positive_price(self):
        p = make_provider()
        for sym in ("SPY", "QQQ", "AAPL", "MSFT", "TSLA", "NVDA", "AMD", "AMZN"):
            assert p.get_latest_price(sym) > 0, f"{sym} returned non-positive price"


# ---------------------------------------------------------------------------
# get_historical_bars — column contracts
# ---------------------------------------------------------------------------

class TestGetHistoricalBarsColumns:
    def test_returns_all_ohlcv_columns(self):
        df = make_bars()
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns, f"Missing column: {col}"

    def test_result_is_nonempty(self):
        df = make_bars(days=5)
        assert len(df) > 0


# ---------------------------------------------------------------------------
# get_historical_bars — price validity
# ---------------------------------------------------------------------------

class TestGetHistoricalBarsPrices:
    def test_close_prices_are_positive(self):
        df = make_bars()
        assert (df["close"] > 0).all()

    def test_volume_is_positive(self):
        df = make_bars()
        assert (df["volume"] > 0).all()

    def test_high_is_always_gte_low(self):
        df = make_bars()
        assert (df["high"] >= df["low"]).all()

    def test_high_is_always_gte_open(self):
        df = make_bars()
        assert (df["high"] >= df["open"]).all()

    def test_low_is_always_lte_close(self):
        df = make_bars()
        assert (df["low"] <= df["close"]).all()


# ---------------------------------------------------------------------------
# get_historical_bars — unknown symbol
# ---------------------------------------------------------------------------

class TestGetHistoricalBarsUnknownSymbol:
    def test_unknown_symbol_still_returns_dataframe(self):
        p = make_provider()
        end = datetime(2024, 6, 1)
        df = p.get_historical_bars("FAKE", end - timedelta(days=5), end, "1Day")
        assert df is not None
        assert len(df) > 0
