"""
TitanAlpacaConnector — BrokerageHandler layer that bridges Titan ML signals
to live Alpaca order execution.

Architecture role:
    Live Data Feed → ML Inference → [TitanAlpacaConnector] → Alpaca Orders
                                         ↕
                                   RiskEngine / Circuit Breaker
"""

import logging
import math
import os
from typing import Any, Dict, Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

logger = logging.getLogger("TitanAlpacaConnector")

# Maps string signals (from SignalEngine) to integer values
_SIGNAL_MAP: Dict[str, int] = {"BUY": 1, "SELL": -1, "HOLD": 0}


class TitanAlpacaConnector:
    """
    Singleton BrokerageHandler that translates Titan ML signals into Alpaca
    market orders.

    Signal contract:
        1  (or "BUY")  → market BUY
       -1  (or "SELL") → market SELL
        0  (or "HOLD") → no action

    Enterprise controls built in:
        • Confidence threshold gate — ignores low-confidence predictions.
        • Dynamic position sizing   — scales qty by confidence × equity × risk%.
        • Kill switch               — halts ALL order submission immediately.
        • Manual approval mode      — signals are logged but NOT auto-submitted
                                      (rollback triggered by poor model metrics).
    """

    _instance: Optional["TitanAlpacaConnector"] = None

    # ------------------------------------------------------------------
    # Singleton factory
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "TitanAlpacaConnector":
        """Return (or create) the singleton connector."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")

        # paper=True  →  paper-trading endpoint (safe default)
        # paper=False →  live endpoint  (requires EXECUTION_MODE=live)
        self.paper: bool = os.getenv("EXECUTION_MODE", "paper").strip().lower() != "live"

        self.min_confidence: float = float(os.getenv("ALPACA_MIN_CONFIDENCE", "0.60"))
        self.risk_per_trade_pct: float = float(os.getenv("ALPACA_RISK_PER_TRADE", "0.02"))

        # Enterprise control flags
        self._kill_switch_active: bool = False
        self._manual_approval_mode: bool = False

        if not self.api_key or not self.secret_key:
            raise ValueError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in environment."
            )

        self.trading_client = TradingClient(
            self.api_key, self.secret_key, paper=self.paper
        )

        mode_label = "PAPER" if self.paper else "LIVE"
        logger.info(
            f"TitanAlpacaConnector initialised | mode={mode_label} "
            f"| min_confidence={self.min_confidence:.0%} "
            f"| risk_per_trade={self.risk_per_trade_pct:.1%}"
        )

    # ------------------------------------------------------------------
    # Circuit-breaker controls
    # ------------------------------------------------------------------

    def activate_kill_switch(self) -> None:
        """
        Hard kill switch — immediately stops ALL order submission.
        Call this when the daily drawdown limit is breached.
        """
        self._kill_switch_active = True
        logger.critical(
            "KILL SWITCH ACTIVATED — all order submission is HALTED. "
            "Call liquidate_all() to close open positions."
        )

    def deactivate_kill_switch(self) -> None:
        """Re-enable automated trading after manual review."""
        self._kill_switch_active = False
        logger.warning("Kill switch deactivated. Automated trading resumed.")

    def activate_manual_approval_mode(self) -> None:
        """
        Rollback to manual-approval mode.
        Signals are logged but NOT auto-submitted to Alpaca.
        Triggered when model Sharpe / accuracy falls below thresholds.
        """
        self._manual_approval_mode = True
        logger.warning(
            "MANUAL APPROVAL MODE ACTIVE — signals are logged but will NOT be "
            "auto-executed until this mode is deactivated."
        )

    def deactivate_manual_approval_mode(self) -> None:
        """Resume auto-execution after model performance recovers."""
        self._manual_approval_mode = False
        logger.info("Manual approval mode deactivated. Auto-execution resumed.")

    @property
    def is_blocked(self) -> bool:
        """True when no orders should be submitted (kill switch OR manual mode)."""
        return self._kill_switch_active or self._manual_approval_mode

    # ------------------------------------------------------------------
    # Account helpers
    # ------------------------------------------------------------------

    def get_account(self) -> Dict[str, Any]:
        """
        Return current Alpaca account state as a flat dict.
        Used by the circuit-breaker monitor to compare equity vs starting equity.
        """
        try:
            acct = self.trading_client.get_account()
            return {
                "equity": float(acct.equity),
                "cash": float(acct.cash),
                "buying_power": float(acct.buying_power),
                "portfolio_value": float(acct.portfolio_value),
                "unrealized_pl": float(getattr(acct, "unrealized_pl", 0) or 0),
                "status": str(acct.status),
            }
        except Exception as exc:
            logger.error(f"get_account failed: {exc}")
            return {}

    def _get_equity(self) -> float:
        """Return current equity, or 0 on failure."""
        return self.get_account().get("equity", 0.0)

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def _calculate_qty(self, price: float, confidence: float) -> int:
        """
        Dynamic position sizing using Fixed-Fractional + Confidence scaling.

        Formula:
            qty = floor( equity × risk_per_trade_pct × confidence / price )

        A confidence of 1.0 uses the full risk allocation; lower confidence
        proportionally reduces the position.
        """
        if price <= 0 or confidence <= 0:
            return 0

        equity = self._get_equity()
        if equity <= 0:
            logger.warning("Equity is 0 — cannot size position.")
            return 0

        risk_dollars = equity * self.risk_per_trade_pct * confidence
        qty = math.floor(risk_dollars / price)
        return max(qty, 0)

    # ------------------------------------------------------------------
    # Core signal → order translation
    # ------------------------------------------------------------------

    def execute_signal(
        self,
        symbol: str,
        signal: Any,          # int (-1/0/1) or str ("BUY"/"SELL"/"HOLD")
        confidence: float,
        model_id: str,
        price: float = 0.0,
        model_version: str = "v1.0",
    ) -> Optional[Dict[str, Any]]:
        """
        Translate a Titan ML signal into an Alpaca market order.

        Args:
            symbol:        Ticker (e.g. "AAPL").
            signal:        Model output — int (1/0/-1) or string ("BUY"/"HOLD"/"SELL").
            confidence:    Prediction confidence in [0, 1].
            model_id:      Strategy/model identifier for the audit trail.
            price:         Last known market price used for position sizing.
            model_version: Semantic version tag recorded in audit events.

        Returns:
            Order summary dict on success, None when no order is placed.
        """
        # --- Normalise signal to integer ---
        if isinstance(signal, str):
            signal_int = _SIGNAL_MAP.get(signal.upper(), 0)
        else:
            signal_int = int(signal)

        # --- Gate 1: Kill switch ---
        if self._kill_switch_active:
            logger.warning(
                f"[{model_id}] Signal REJECTED — kill switch active. "
                f"({signal_int} {symbol} conf={confidence:.2%})"
            )
            return None

        # --- Gate 2: Manual approval mode (model rollback) ---
        if self._manual_approval_mode:
            logger.info(
                f"[{model_id}] Signal QUEUED for manual review — "
                f"({signal_int} {symbol} conf={confidence:.2%})"
            )
            return None

        # --- Gate 3: Confidence threshold ---
        if confidence < self.min_confidence:
            logger.debug(
                f"[{model_id}] Signal BELOW confidence threshold "
                f"({confidence:.2%} < {self.min_confidence:.2%}) — skipped."
            )
            return None

        # --- Map signal int to Alpaca OrderSide ---
        if signal_int == 1:
            side = OrderSide.BUY
        elif signal_int == -1:
            side = OrderSide.SELL
        else:
            return None  # HOLD — no action needed

        # --- Dynamic position sizing ---
        qty = self._calculate_qty(price, confidence)
        if qty <= 0:
            logger.warning(
                f"[{model_id}] Calculated qty=0 for {symbol} "
                f"(price={price}, conf={confidence:.2%}). Order skipped."
            )
            return None

        # --- Submit order ---
        order_req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC,
        )

        try:
            order = self.trading_client.submit_order(order_req)
            result = {
                "order_id": str(order.id),
                "model_id": model_id,
                "model_version": model_version,
                "symbol": symbol,
                "side": side.value,
                "qty": qty,
                "confidence": round(confidence, 4),
                "price_at_signal": price,
                "status": str(order.status),
                "mode": "paper" if self.paper else "live",
            }
            logger.info(
                f"ORDER SUBMITTED [{model_id} {model_version}] "
                f"{side.value} {qty} {symbol} | conf={confidence:.2%} "
                f"| order_id={order.id}"
            )
            return result

        except Exception as exc:
            logger.error(
                f"[{model_id}] Order submission FAILED for {symbol}: {exc}"
            )
            raise

    # ------------------------------------------------------------------
    # Emergency operations
    # ------------------------------------------------------------------

    def liquidate_all(self) -> None:
        """
        Emergency close of all open positions and pending orders.
        Called by the circuit breaker when the drawdown limit is breached.
        """
        logger.critical(
            "EMERGENCY LIQUIDATION — closing ALL positions and cancelling orders."
        )
        try:
            self.trading_client.close_all_positions(cancel_orders=True)
            logger.info("Emergency liquidation complete.")
        except Exception as exc:
            logger.error(f"Liquidation failed: {exc}")
