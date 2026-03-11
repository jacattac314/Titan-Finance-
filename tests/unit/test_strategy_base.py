"""
Unit tests for services/signal/strategies/base.py

Covers model_id enforcement: a warning must be emitted and the
sentinel value "unknown_strategy" assigned when model_id is absent
from config.  When model_id IS supplied it must be stored verbatim.
"""
import asyncio
import logging
import pytest
from strategies.base import Strategy


# ---------------------------------------------------------------------------
# Concrete stub — minimal subclass to exercise the base __init__
# ---------------------------------------------------------------------------

class _StubStrategy(Strategy):
    async def on_tick(self, tick): return None
    async def on_bar(self, bar): return None


# ---------------------------------------------------------------------------
# model_id handling
# ---------------------------------------------------------------------------

class TestModelId:
    def test_model_id_stored_when_provided(self):
        s = _StubStrategy({"symbol": "SPY", "model_id": "my_model_v1"})
        assert s.model_id == "my_model_v1"

    def test_model_id_defaults_to_sentinel_when_absent(self):
        s = _StubStrategy({"symbol": "SPY"})
        assert s.model_id == "unknown_strategy"

    def test_model_id_defaults_to_sentinel_when_empty_string(self):
        s = _StubStrategy({"symbol": "SPY", "model_id": ""})
        assert s.model_id == "unknown_strategy"

    def test_warning_emitted_when_model_id_absent(self, caplog):
        with caplog.at_level(logging.WARNING, logger="TitanStrategy"):
            _StubStrategy({"symbol": "SPY"})
        assert any(
            "model_id" in record.message and "without" in record.message
            for record in caplog.records
        ), "Expected a WARNING about missing model_id"

    def test_no_warning_when_model_id_present(self, caplog):
        with caplog.at_level(logging.WARNING, logger="TitanStrategy"):
            _StubStrategy({"symbol": "SPY", "model_id": "some_model"})
        assert not any(
            "model_id" in record.message and "without" in record.message
            for record in caplog.records
        ), "Should not warn when model_id is provided"


# ---------------------------------------------------------------------------
# symbol default
# ---------------------------------------------------------------------------

class TestSymbolDefault:
    def test_symbol_defaults_to_spy(self):
        s = _StubStrategy({"model_id": "x"})
        assert s.symbol == "SPY"

    def test_symbol_overridden_by_config(self):
        s = _StubStrategy({"symbol": "AAPL", "model_id": "x"})
        assert s.symbol == "AAPL"
