"""
TitanFlow Shared Event Schemas

Versioned dataclasses for cross-service message contracts.
All Redis pub/sub messages must conform to these schemas.

schema_version: "1.0"

Usage:
    from schemas import (
        MarketDataEvent,
        TradeSignalEvent,
        ExecutionRequestEvent,
        ExecutionFilledEvent,
        validate_and_log,
        SchemaValidationError,
        SCHEMA_VERSION,
    )

Producers:
    event = TradeSignalEvent(...)
    await redis.publish("trade_signals", json.dumps(event.to_dict()))

Consumers:
    data = json.loads(message["data"])
    event = validate_and_log(TradeSignalEvent, data, context="signal->risk")
    if event is None:
        continue  # validation failure already logged
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"

logger = logging.getLogger(__name__)


class SchemaValidationError(ValueError):
    """Raised when a message payload fails schema validation."""


# ---------------------------------------------------------------------------
# Event: market_data
# ---------------------------------------------------------------------------

@dataclass
class MarketDataEvent:
    """Published to channel: market_data (by gateway service)."""

    symbol: str
    price: float
    timestamp: str
    type: str = "trade"
    volume: int = 0
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketDataEvent":
        required = {"symbol", "price", "timestamp"}
        missing = required - data.keys()
        if missing:
            raise SchemaValidationError(
                f"MarketDataEvent missing required fields: {missing}"
            )
        price = float(data["price"])
        if price <= 0:
            raise SchemaValidationError(
                f"MarketDataEvent.price must be > 0, got {price}"
            )
        return cls(
            symbol=str(data["symbol"]),
            price=price,
            timestamp=str(data["timestamp"]),
            type=str(data.get("type", "trade")),
            volume=int(data.get("volume", 0)),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Event: trade_signals
# ---------------------------------------------------------------------------

@dataclass
class TradeSignalEvent:
    """Published to channel: trade_signals (by signal service)."""

    model_id: str
    symbol: str
    signal: str        # "BUY" | "SELL" | "HOLD"
    confidence: float
    timestamp: str
    price: float = 0.0
    explanation: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    _VALID_SIGNALS = frozenset({"BUY", "SELL", "HOLD"})

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeSignalEvent":
        required = {"model_id", "symbol", "signal", "confidence", "timestamp"}
        missing = required - data.keys()
        if missing:
            raise SchemaValidationError(
                f"TradeSignalEvent missing required fields: {missing}"
            )
        signal = str(data["signal"]).upper()
        if signal not in cls._VALID_SIGNALS:
            raise SchemaValidationError(
                f"TradeSignalEvent.signal must be one of {set(cls._VALID_SIGNALS)}, "
                f"got '{signal}'"
            )
        confidence = float(data["confidence"])
        if not (0.0 <= confidence <= 1.0):
            raise SchemaValidationError(
                f"TradeSignalEvent.confidence must be in [0, 1], got {confidence}"
            )
        return cls(
            model_id=str(data["model_id"]),
            symbol=str(data["symbol"]),
            signal=signal,
            confidence=confidence,
            timestamp=str(data["timestamp"]),
            price=float(data.get("price", 0.0)),
            explanation=list(data.get("explanation", [])),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Event: execution_requests
# ---------------------------------------------------------------------------

@dataclass
class ExecutionRequestEvent:
    """Published to channel: execution_requests (by risk service after approval).

    Side is lowercase ("buy"/"sell") to match risk service convention.
    qty is pre-calculated by the risk engine (fixed-fractional position sizing).
    """

    model_id: str
    symbol: str
    side: str          # "buy" | "sell" (lowercase)
    qty: int
    confidence: float
    timestamp: str
    type: str = "market"
    price: Optional[float] = None
    explanation: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    _VALID_SIDES = frozenset({"buy", "sell"})

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionRequestEvent":
        required = {"model_id", "symbol", "side", "qty", "confidence", "timestamp"}
        missing = required - data.keys()
        if missing:
            raise SchemaValidationError(
                f"ExecutionRequestEvent missing required fields: {missing}"
            )
        side = str(data["side"]).lower()
        if side not in cls._VALID_SIDES:
            raise SchemaValidationError(
                f"ExecutionRequestEvent.side must be one of {set(cls._VALID_SIDES)}, "
                f"got '{side}'"
            )
        qty = int(data["qty"])
        if qty <= 0:
            raise SchemaValidationError(
                f"ExecutionRequestEvent.qty must be > 0, got {qty}"
            )
        return cls(
            model_id=str(data["model_id"]),
            symbol=str(data["symbol"]),
            side=side,
            qty=qty,
            confidence=float(data["confidence"]),
            timestamp=str(data["timestamp"]),
            type=str(data.get("type", "market")),
            price=float(data["price"]) if data.get("price") is not None else None,
            explanation=list(data.get("explanation", [])),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Event: execution_filled
# ---------------------------------------------------------------------------

@dataclass
class ExecutionFilledEvent:
    """Published to channel: execution_filled (by execution service)."""

    id: str
    order_id: str
    model_id: str
    symbol: str
    side: str          # "BUY" | "SELL" (uppercase)
    qty: int
    price: float
    timestamp: str
    status: str = "FILLED"
    mode: str = "paper"   # "paper" | "live"
    slippage: float = 0.0
    explanation: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionFilledEvent":
        required = {"id", "order_id", "model_id", "symbol", "side", "qty", "price", "timestamp"}
        missing = required - data.keys()
        if missing:
            raise SchemaValidationError(
                f"ExecutionFilledEvent missing required fields: {missing}"
            )
        return cls(
            id=str(data["id"]),
            order_id=str(data["order_id"]),
            model_id=str(data["model_id"]),
            symbol=str(data["symbol"]),
            side=str(data["side"]).upper(),
            qty=int(data["qty"]),
            price=float(data["price"]),
            timestamp=str(data["timestamp"]),
            status=str(data.get("status", "FILLED")),
            mode=str(data.get("mode", "paper")),
            slippage=float(data.get("slippage", 0.0)),
            explanation=list(data.get("explanation", [])),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def validate_and_log(
    event_cls: type,
    data: Dict[str, Any],
    context: str = "",
) -> Optional[Any]:
    """Attempt to validate *data* against *event_cls.from_dict()*.

    On validation failure:
      - Logs a structured warning with schema name, error, and payload keys.
      - Returns None so the caller can ``continue`` the message loop.

    On success:
      - Returns the validated event instance.

    Example::

        event = validate_and_log(TradeSignalEvent, payload, context="risk:consume")
        if event is None:
            continue
    """
    try:
        return event_cls.from_dict(data)
    except SchemaValidationError as exc:
        logger.warning(
            "[%s] %s validation failed: %s | payload_keys=%s",
            context,
            event_cls.__name__,
            exc,
            sorted(data.keys()),
        )
        return None
    except Exception as exc:
        logger.error(
            "[%s] Unexpected error validating %s: %s",
            context,
            event_cls.__name__,
            exc,
        )
        return None
