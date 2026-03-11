"""
E2E channel contract tests: signal → risk → execution schema pipeline.

Validates that:
1. Signal payloads produced by strategies conform to the TradeSignalEvent schema
   that the risk service consumes.
2. Risk-approved payloads conform to the ExecutionRequestEvent schema the
   execution service expects.

No real Redis is required — these are pure schema-validation unit tests.
"""
import pytest

from schemas import (
    TradeSignalEvent,
    ExecutionRequestEvent,
    validate_and_log,
    SchemaValidationError,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers — payload builders
# ---------------------------------------------------------------------------

def _valid_trade_signal(**overrides) -> dict:
    """Return a minimal valid TradeSignalEvent dict."""
    base = {
        "model_id": "sma_spy",
        "symbol": "SPY",
        "signal": "BUY",
        "confidence": 0.75,
        "timestamp": "2024-01-01T14:30:00Z",
        "price": 450.0,
        "explanation": ["fast_ma > slow_ma"],
        "schema_version": SCHEMA_VERSION,
    }
    base.update(overrides)
    return base


def _valid_execution_request(**overrides) -> dict:
    """Return a minimal valid ExecutionRequestEvent dict (risk-approved)."""
    base = {
        "model_id": "sma_spy",
        "symbol": "SPY",
        "side": "buy",
        "qty": 10,
        "confidence": 0.75,
        "timestamp": "2024-01-01T14:30:00Z",
        "type": "market",
        "explanation": ["fast_ma > slow_ma"],
        "schema_version": SCHEMA_VERSION,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TradeSignalEvent contract tests
# ---------------------------------------------------------------------------

class TestTradeSignalEventContract:
    """Validate TradeSignalEvent schema acceptance and rejection rules."""

    def test_valid_trade_signal_passes_validation(self):
        """A complete, well-formed TradeSignalEvent dict passes validate_and_log."""
        data = _valid_trade_signal()
        result = validate_and_log(TradeSignalEvent, data, context="test:trade_signal:valid")
        assert result is not None, (
            "validate_and_log must return a TradeSignalEvent instance for a valid payload"
        )
        assert isinstance(result, TradeSignalEvent)

    def test_trade_signal_missing_model_id_fails_validation(self):
        """A TradeSignalEvent missing the required 'model_id' field must fail validation."""
        data = _valid_trade_signal()
        del data["model_id"]
        result = validate_and_log(TradeSignalEvent, data, context="test:trade_signal:missing_model_id")
        assert result is None, (
            "validate_and_log must return None when 'model_id' is absent"
        )

    def test_trade_signal_missing_symbol_fails_validation(self):
        """A TradeSignalEvent missing 'symbol' must fail validation."""
        data = _valid_trade_signal()
        del data["symbol"]
        result = validate_and_log(TradeSignalEvent, data, context="test:trade_signal:missing_symbol")
        assert result is None

    def test_trade_signal_missing_signal_field_fails_validation(self):
        """A TradeSignalEvent missing 'signal' must fail validation."""
        data = _valid_trade_signal()
        del data["signal"]
        result = validate_and_log(TradeSignalEvent, data, context="test:trade_signal:missing_signal")
        assert result is None

    def test_trade_signal_invalid_signal_value_fails_validation(self):
        """A TradeSignalEvent with an unrecognised signal value must fail validation."""
        data = _valid_trade_signal(signal="STRONG_BUY")
        result = validate_and_log(TradeSignalEvent, data, context="test:trade_signal:invalid_signal_value")
        assert result is None

    def test_trade_signal_confidence_out_of_range_fails_validation(self):
        """Confidence > 1.0 must fail TradeSignalEvent validation."""
        data = _valid_trade_signal(confidence=1.5)
        result = validate_and_log(TradeSignalEvent, data, context="test:trade_signal:confidence_oob")
        assert result is None

    def test_trade_signal_schema_version_field_is_present(self):
        """Validated TradeSignalEvent must carry a schema_version field."""
        data = _valid_trade_signal()
        result = validate_and_log(TradeSignalEvent, data, context="test:trade_signal:schema_version")
        assert result is not None
        assert hasattr(result, "schema_version"), (
            "TradeSignalEvent must expose a schema_version attribute"
        )
        assert result.schema_version == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# ExecutionRequestEvent contract tests
# ---------------------------------------------------------------------------

class TestExecutionRequestEventContract:
    """Validate ExecutionRequestEvent schema acceptance and rejection rules."""

    def test_valid_execution_request_passes_validation(self):
        """A complete, well-formed ExecutionRequestEvent dict passes validate_and_log."""
        data = _valid_execution_request()
        result = validate_and_log(ExecutionRequestEvent, data, context="test:exec_request:valid")
        assert result is not None, (
            "validate_and_log must return an ExecutionRequestEvent instance for a valid payload"
        )
        assert isinstance(result, ExecutionRequestEvent)

    def test_execution_request_negative_qty_fails_validation(self):
        """An ExecutionRequestEvent with qty <= 0 must fail validation."""
        data = _valid_execution_request(qty=-5)
        result = validate_and_log(ExecutionRequestEvent, data, context="test:exec_request:negative_qty")
        assert result is None, (
            "validate_and_log must return None when qty is negative"
        )

    def test_execution_request_zero_qty_fails_validation(self):
        """An ExecutionRequestEvent with qty=0 must fail validation."""
        data = _valid_execution_request(qty=0)
        result = validate_and_log(ExecutionRequestEvent, data, context="test:exec_request:zero_qty")
        assert result is None

    def test_execution_request_invalid_side_fails_validation(self):
        """An ExecutionRequestEvent with side='hold' must fail validation."""
        data = _valid_execution_request(side="hold")
        result = validate_and_log(ExecutionRequestEvent, data, context="test:exec_request:invalid_side")
        assert result is None

    def test_execution_request_missing_qty_fails_validation(self):
        """An ExecutionRequestEvent missing 'qty' must fail validation."""
        data = _valid_execution_request()
        del data["qty"]
        result = validate_and_log(ExecutionRequestEvent, data, context="test:exec_request:missing_qty")
        assert result is None

    def test_execution_request_schema_version_field_is_present(self):
        """Validated ExecutionRequestEvent must carry a schema_version field."""
        data = _valid_execution_request()
        result = validate_and_log(ExecutionRequestEvent, data, context="test:exec_request:schema_version")
        assert result is not None
        assert hasattr(result, "schema_version"), (
            "ExecutionRequestEvent must expose a schema_version attribute"
        )
        assert result.schema_version == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Round-trip test: build → to_dict → validate_and_log
# ---------------------------------------------------------------------------

class TestSchemaRoundTrip:
    """Validate that to_dict() output round-trips cleanly through validate_and_log."""

    def test_trade_signal_round_trip(self):
        """Build a TradeSignalEvent, call to_dict(), pass through validate_and_log,
        and assert the result equals the original instance."""
        original = TradeSignalEvent(
            model_id="sma_spy",
            symbol="SPY",
            signal="BUY",
            confidence=0.75,
            timestamp="2024-01-01T14:30:00Z",
            price=450.0,
            explanation=["fast_ma > slow_ma"],
            schema_version=SCHEMA_VERSION,
        )
        serialised = original.to_dict()
        result = validate_and_log(
            TradeSignalEvent, serialised, context="test:round_trip:trade_signal"
        )
        assert result is not None, (
            "Round-trip through to_dict() → validate_and_log must not fail"
        )
        assert result.model_id == original.model_id
        assert result.symbol == original.symbol
        assert result.signal == original.signal
        assert result.confidence == original.confidence
        assert result.timestamp == original.timestamp
        assert result.price == original.price
        assert result.explanation == original.explanation
        assert result.schema_version == original.schema_version

    def test_execution_request_round_trip(self):
        """Build an ExecutionRequestEvent, call to_dict(), pass through validate_and_log,
        and assert the result equals the original instance."""
        original = ExecutionRequestEvent(
            model_id="sma_spy",
            symbol="SPY",
            side="buy",
            qty=10,
            confidence=0.75,
            timestamp="2024-01-01T14:30:00Z",
            type="market",
            price=None,
            explanation=["fast_ma > slow_ma"],
            schema_version=SCHEMA_VERSION,
        )
        serialised = original.to_dict()
        result = validate_and_log(
            ExecutionRequestEvent, serialised, context="test:round_trip:exec_request"
        )
        assert result is not None, (
            "Round-trip through to_dict() → validate_and_log must not fail"
        )
        assert result.model_id == original.model_id
        assert result.symbol == original.symbol
        assert result.side == original.side
        assert result.qty == original.qty
        assert result.confidence == original.confidence
        assert result.timestamp == original.timestamp
        assert result.schema_version == original.schema_version


# ---------------------------------------------------------------------------
# Schema version presence across both event types
# ---------------------------------------------------------------------------

class TestSchemaVersionPresence:
    """Assert schema_version is defined on both event types and matches SCHEMA_VERSION."""

    def test_trade_signal_event_has_schema_version_default(self):
        """TradeSignalEvent instances must carry schema_version == SCHEMA_VERSION by default."""
        event = TradeSignalEvent(
            model_id="m1",
            symbol="SPY",
            signal="SELL",
            confidence=0.6,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert event.schema_version == SCHEMA_VERSION

    def test_execution_request_event_has_schema_version_default(self):
        """ExecutionRequestEvent instances must carry schema_version == SCHEMA_VERSION by default."""
        event = ExecutionRequestEvent(
            model_id="m1",
            symbol="SPY",
            side="sell",
            qty=5,
            confidence=0.6,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert event.schema_version == SCHEMA_VERSION

    def test_schema_version_preserved_through_serialisation(self):
        """schema_version must survive a to_dict() → from_dict() round-trip."""
        original = TradeSignalEvent(
            model_id="m1",
            symbol="SPY",
            signal="HOLD",
            confidence=0.5,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert original.to_dict()["schema_version"] == SCHEMA_VERSION
        restored = TradeSignalEvent.from_dict(original.to_dict())
        assert restored.schema_version == SCHEMA_VERSION
