"""
Unit tests for shared event schemas (shared/schemas.py).

Tests cover:
- Required field enforcement for each event type.
- Field coercion and normalisation (e.g. side → lowercase, signal → uppercase).
- Enum / range validation.
- validate_and_log() helper: returns None on failure without raising.
- to_dict() round-trip includes schema_version.
"""
import pathlib
import sys

# Make shared/ importable when running from project root via pytest.
_SHARED = pathlib.Path(__file__).parent.parent.parent / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import pytest
from schemas import (
    SCHEMA_VERSION,
    ExecutionFilledEvent,
    ExecutionRequestEvent,
    MarketDataEvent,
    SchemaValidationError,
    TradeSignalEvent,
    validate_and_log,
)


# ---------------------------------------------------------------------------
# MarketDataEvent
# ---------------------------------------------------------------------------

class TestMarketDataEvent:
    def _valid(self, **overrides):
        base = {"symbol": "SPY", "price": 450.0, "timestamp": "2024-01-01T14:30:00Z"}
        base.update(overrides)
        return base

    def test_valid_payload_parses(self):
        evt = MarketDataEvent.from_dict(self._valid())
        assert evt.symbol == "SPY"
        assert evt.price == 450.0
        assert evt.schema_version == SCHEMA_VERSION

    def test_missing_symbol_raises(self):
        with pytest.raises(SchemaValidationError, match="symbol"):
            MarketDataEvent.from_dict({"price": 100.0, "timestamp": "t"})

    def test_missing_price_raises(self):
        with pytest.raises(SchemaValidationError, match="price"):
            MarketDataEvent.from_dict({"symbol": "SPY", "timestamp": "t"})

    def test_zero_price_raises(self):
        with pytest.raises(SchemaValidationError, match="price"):
            MarketDataEvent.from_dict(self._valid(price=0.0))

    def test_negative_price_raises(self):
        with pytest.raises(SchemaValidationError, match="price"):
            MarketDataEvent.from_dict(self._valid(price=-5.0))

    def test_to_dict_round_trip(self):
        evt = MarketDataEvent.from_dict(self._valid())
        d = evt.to_dict()
        assert d["symbol"] == "SPY"
        assert d["schema_version"] == SCHEMA_VERSION

    def test_schema_version_preserved_from_payload(self):
        evt = MarketDataEvent.from_dict(self._valid(schema_version="0.9"))
        assert evt.schema_version == "0.9"

    def test_defaults_applied(self):
        evt = MarketDataEvent.from_dict(self._valid())
        assert evt.type == "trade"
        assert evt.volume == 0


# ---------------------------------------------------------------------------
# TradeSignalEvent
# ---------------------------------------------------------------------------

class TestTradeSignalEvent:
    def _valid(self, **overrides):
        base = {
            "model_id": "sma_spy",
            "symbol": "SPY",
            "signal": "BUY",
            "confidence": 0.75,
            "timestamp": "2024-01-01T14:30:00Z",
            "price": 450.0,
        }
        base.update(overrides)
        return base

    def test_valid_buy(self):
        evt = TradeSignalEvent.from_dict(self._valid())
        assert evt.signal == "BUY"
        assert evt.schema_version == SCHEMA_VERSION

    def test_valid_sell(self):
        evt = TradeSignalEvent.from_dict(self._valid(signal="SELL"))
        assert evt.signal == "SELL"

    def test_valid_hold(self):
        evt = TradeSignalEvent.from_dict(self._valid(signal="HOLD"))
        assert evt.signal == "HOLD"

    def test_signal_normalised_to_uppercase(self):
        evt = TradeSignalEvent.from_dict(self._valid(signal="buy"))
        assert evt.signal == "BUY"

    def test_invalid_signal_raises(self):
        with pytest.raises(SchemaValidationError, match="signal"):
            TradeSignalEvent.from_dict(self._valid(signal="LONG"))

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(SchemaValidationError, match="confidence"):
            TradeSignalEvent.from_dict(self._valid(confidence=1.5))

    def test_negative_confidence_raises(self):
        with pytest.raises(SchemaValidationError, match="confidence"):
            TradeSignalEvent.from_dict(self._valid(confidence=-0.1))

    def test_missing_model_id_raises(self):
        d = self._valid()
        d.pop("model_id")
        with pytest.raises(SchemaValidationError, match="model_id"):
            TradeSignalEvent.from_dict(d)

    def test_to_dict_includes_schema_version(self):
        d = TradeSignalEvent.from_dict(self._valid()).to_dict()
        assert d["schema_version"] == SCHEMA_VERSION

    def test_explanation_defaults_to_empty_list(self):
        evt = TradeSignalEvent.from_dict(self._valid())
        assert evt.explanation == []


# ---------------------------------------------------------------------------
# ExecutionRequestEvent
# ---------------------------------------------------------------------------

class TestExecutionRequestEvent:
    def _valid(self, **overrides):
        base = {
            "model_id": "sma_spy",
            "symbol": "SPY",
            "side": "buy",
            "qty": 10,
            "confidence": 0.75,
            "timestamp": "2024-01-01T14:30:00Z",
        }
        base.update(overrides)
        return base

    def test_valid_buy(self):
        evt = ExecutionRequestEvent.from_dict(self._valid())
        assert evt.side == "buy"
        assert evt.qty == 10

    def test_valid_sell(self):
        evt = ExecutionRequestEvent.from_dict(self._valid(side="sell"))
        assert evt.side == "sell"

    def test_side_normalised_to_lowercase(self):
        evt = ExecutionRequestEvent.from_dict(self._valid(side="BUY"))
        assert evt.side == "buy"

    def test_invalid_side_raises(self):
        with pytest.raises(SchemaValidationError, match="side"):
            ExecutionRequestEvent.from_dict(self._valid(side="HOLD"))

    def test_zero_qty_raises(self):
        with pytest.raises(SchemaValidationError, match="qty"):
            ExecutionRequestEvent.from_dict(self._valid(qty=0))

    def test_negative_qty_raises(self):
        with pytest.raises(SchemaValidationError, match="qty"):
            ExecutionRequestEvent.from_dict(self._valid(qty=-5))

    def test_missing_qty_raises(self):
        d = self._valid()
        d.pop("qty")
        with pytest.raises(SchemaValidationError, match="qty"):
            ExecutionRequestEvent.from_dict(d)

    def test_optional_price_is_none_when_absent(self):
        evt = ExecutionRequestEvent.from_dict(self._valid())
        assert evt.price is None

    def test_optional_price_parsed_when_present(self):
        evt = ExecutionRequestEvent.from_dict(self._valid(price=300.0))
        assert evt.price == 300.0

    def test_to_dict_round_trip(self):
        d = ExecutionRequestEvent.from_dict(self._valid()).to_dict()
        assert d["side"] == "buy"
        assert d["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# ExecutionFilledEvent
# ---------------------------------------------------------------------------

class TestExecutionFilledEvent:
    def _valid(self, **overrides):
        base = {
            "id": "fill-001",
            "order_id": "order-001",
            "model_id": "sma_spy",
            "symbol": "SPY",
            "side": "BUY",
            "qty": 10,
            "price": 451.5,
            "timestamp": "2024-01-01T14:30:00Z",
        }
        base.update(overrides)
        return base

    def test_valid_fill(self):
        evt = ExecutionFilledEvent.from_dict(self._valid())
        assert evt.status == "FILLED"
        assert evt.mode == "paper"

    def test_side_normalised_to_uppercase(self):
        evt = ExecutionFilledEvent.from_dict(self._valid(side="buy"))
        assert evt.side == "BUY"

    def test_missing_id_raises(self):
        d = self._valid()
        d.pop("id")
        with pytest.raises(SchemaValidationError, match="id"):
            ExecutionFilledEvent.from_dict(d)

    def test_missing_price_raises(self):
        d = self._valid()
        d.pop("price")
        with pytest.raises(SchemaValidationError, match="price"):
            ExecutionFilledEvent.from_dict(d)

    def test_to_dict_includes_all_required_fields(self):
        d = ExecutionFilledEvent.from_dict(self._valid()).to_dict()
        required = {"id", "order_id", "model_id", "symbol", "side", "qty", "price", "timestamp"}
        assert required.issubset(d.keys())
        assert d["schema_version"] == SCHEMA_VERSION

    def test_slippage_defaults_to_zero(self):
        evt = ExecutionFilledEvent.from_dict(self._valid())
        assert evt.slippage == 0.0


# ---------------------------------------------------------------------------
# validate_and_log helper
# ---------------------------------------------------------------------------

class TestValidateAndLog:
    def test_returns_event_on_success(self):
        data = {
            "symbol": "SPY",
            "price": 100.0,
            "timestamp": "2024-01-01T00:00:00Z",
        }
        result = validate_and_log(MarketDataEvent, data, context="test")
        assert result is not None
        assert isinstance(result, MarketDataEvent)

    def test_returns_none_on_validation_failure(self):
        result = validate_and_log(MarketDataEvent, {"price": 100.0}, context="test")
        assert result is None

    def test_returns_none_on_type_error(self):
        result = validate_and_log(MarketDataEvent, {"symbol": "X", "price": "not-a-number", "timestamp": "t"}, context="test")
        assert result is None

    def test_does_not_raise_on_failure(self):
        # Must never propagate an exception — only return None and log.
        validate_and_log(TradeSignalEvent, {}, context="test")  # missing all fields
