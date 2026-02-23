"""
TradeAuditLogger — Centralized MLOps audit trail for Titan Finance.

Every signal, order, fill, kill-switch event, and model-rollback is
persisted as a newline-delimited JSON record (JSONL) to an append-only
log file.  Each record is also published to the Redis channel
``audit_events`` so the operator dashboard can stream audit data in
real time.

Record schema (all events share these base fields):
    event_type      : SIGNAL | ORDER | FILL | KILL_SWITCH | MANUAL_APPROVAL_MODE
    logged_at       : ISO-8601 UTC timestamp (added automatically)
    model_id        : Strategy/model identifier
    model_version   : Semantic version (e.g. "v1.0")

Additional fields vary by event_type — see individual log_* methods.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TitanAuditLog")

_DEFAULT_LOG_PATH = "./logs/trade_audit.jsonl"


class TradeAuditLogger:
    """
    Singleton audit logger.

    Usage:
        audit = TradeAuditLogger.get_instance()
        audit.log_signal(model_id="sma_spy", model_version="v1.0", ...)
        audit.log_order(...)
        audit.log_fill(fill_event, model_version="v1.0")
    """

    _instance: Optional["TradeAuditLogger"] = None

    # ------------------------------------------------------------------
    # Singleton factory
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "TradeAuditLogger":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self.log_path = os.getenv("AUDIT_LOG_PATH", _DEFAULT_LOG_PATH)
        self._redis_client = None  # Injected via set_redis_client()

        # Ensure parent directory exists
        log_dir = os.path.dirname(self.log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        logger.info(f"TradeAuditLogger initialised → {self.log_path}")

    def set_redis_client(self, redis_client: Any) -> None:
        """
        Inject an async Redis client so audit events are also streamed
        to the ``audit_events`` Pub/Sub channel.
        """
        self._redis_client = redis_client

    # ------------------------------------------------------------------
    # Internal write helper
    # ------------------------------------------------------------------

    def _build_record(self, event_type: str, **kwargs: Any) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "event_type": event_type,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        record.update(kwargs)
        return record

    def _write(self, record: Dict[str, Any]) -> None:
        """Append JSON record to JSONL file."""
        try:
            with open(self.log_path, "a") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.error(f"Audit log disk write failed: {exc}")

    async def _publish(self, record: Dict[str, Any]) -> None:
        """Publish record to Redis audit_events channel (async, best-effort)."""
        if self._redis_client is None:
            return
        try:
            await self._redis_client.publish("audit_events", json.dumps(record))
        except Exception as exc:
            logger.warning(f"Audit Redis publish failed (non-fatal): {exc}")

    async def _emit(self, event_type: str, **kwargs: Any) -> None:
        """Write to disk and publish to Redis."""
        record = self._build_record(event_type, **kwargs)
        self._write(record)
        await self._publish(record)

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    async def log_signal(
        self,
        model_id: str,
        model_version: str,
        symbol: str,
        signal: str,
        confidence: float,
        price: float,
        explanation: Optional[List[Any]] = None,
    ) -> None:
        """
        Record an inbound ML signal before any execution gate is applied.

        Args:
            model_id:      Strategy/model identifier (e.g. "lgb_spy_v1").
            model_version: Semantic version for traceability (e.g. "v1.2").
            symbol:        Ticker symbol (e.g. "SPY").
            signal:        Signal value: "BUY", "SELL", or "HOLD".
            confidence:    Model confidence in [0, 1].
            price:         Market price at signal time.
            explanation:   Optional SHAP top-features list for XAI audit.
        """
        await self._emit(
            "SIGNAL",
            model_id=model_id,
            model_version=model_version,
            symbol=symbol,
            signal=signal,
            confidence=round(confidence, 4),
            price=price,
            explanation=explanation or [],
        )

    async def log_order(
        self,
        model_id: str,
        model_version: str,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        confidence: float,
        order_id: str,
        status: str,
        mode: str = "live",
    ) -> None:
        """
        Record a submitted order.  Called immediately after a successful
        ``execute_signal()`` call on TitanAlpacaConnector.
        """
        await self._emit(
            "ORDER",
            model_id=model_id,
            model_version=model_version,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            confidence=round(confidence, 4),
            order_id=order_id,
            status=status,
            mode=mode,
        )

    async def log_fill(
        self,
        fill_event: Dict[str, Any],
        model_version: str = "v1.0",
    ) -> None:
        """
        Record a trade fill (paper or live).

        Args:
            fill_event:    Dict from the execution layer containing at minimum:
                           symbol, side, qty, price, model_id, status.
            model_version: Semantic version to attach to the fill record.
        """
        await self._emit("FILL", model_version=model_version, **fill_event)

    async def log_kill_switch(
        self,
        trigger: str,
        drawdown_pct: float,
        equity: float,
        model_id: str = "system",
        model_version: str = "v1.0",
    ) -> None:
        """
        Record a kill-switch activation.

        Args:
            trigger:      Human-readable cause (e.g. "drawdown > 3%").
            drawdown_pct: Observed drawdown percentage (negative = loss).
            equity:       Current portfolio equity at trigger time.
        """
        await self._emit(
            "KILL_SWITCH",
            model_id=model_id,
            model_version=model_version,
            trigger=trigger,
            drawdown_pct=round(drawdown_pct, 4),
            equity=equity,
        )

    async def log_manual_approval_mode(
        self,
        trigger: str,
        reason: str,
        metric_name: str = "",
        metric_value: float = 0.0,
        threshold: float = 0.0,
        model_id: str = "system",
        model_version: str = "v1.0",
    ) -> None:
        """
        Record a rollback to manual-approval mode.

        Args:
            trigger:      Cause label (e.g. "sharpe_below_threshold").
            reason:       Full description for audit reviewers.
            metric_name:  Name of the metric that triggered rollback (e.g. "sharpe").
            metric_value: Observed metric value.
            threshold:    The configured minimum threshold.
        """
        await self._emit(
            "MANUAL_APPROVAL_MODE",
            model_id=model_id,
            model_version=model_version,
            trigger=trigger,
            reason=reason,
            metric_name=metric_name,
            metric_value=round(metric_value, 4),
            threshold=round(threshold, 4),
        )
