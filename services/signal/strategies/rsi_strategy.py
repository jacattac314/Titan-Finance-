"""
RSI Mean-Reversion Strategy
============================
Generates BUY signals when RSI falls below the oversold threshold (default 30)
and SELL signals when RSI rises above the overbought threshold (default 70).

Signal confidence is proportional to how far RSI has moved past the threshold,
so extreme readings generate higher-confidence signals.
"""

import logging
from collections import deque
from typing import Any, Deque, Dict, Optional

from .base import Strategy

logger = logging.getLogger("TitanRSIMeanReversion")


class RSIMeanReversion(Strategy):
    """
    RSI Mean-Reversion strategy using Wilder's smoothed RSI (simple
    average RSI for the first period, then Wilder's EMA thereafter).

    Config keys:
        symbol          — ticker to trade (default "SPY")
        model_id        — unique identifier for this contender
        rsi_period      — RSI look-back window in ticks (default 14)
        oversold        — RSI level below which a BUY is triggered (default 30)
        overbought      — RSI level above which a SELL is triggered (default 70)
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.period: int = int(config.get("rsi_period", 14))
        self.oversold: float = float(config.get("oversold", 30.0))
        self.overbought: float = float(config.get("overbought", 70.0))

        # Ring buffer of the last (period + 1) prices — enough for one RSI calc
        self.prices: Deque[float] = deque(maxlen=self.period + 1)
        self.current_position: Optional[str] = None  # "LONG", "SHORT", or None

    # ------------------------------------------------------------------
    # RSI calculation (Wilder's simple average — no EMA smoothing for MVP)
    # ------------------------------------------------------------------

    def _compute_rsi(self) -> Optional[float]:
        """Return the current RSI value, or None if insufficient data."""
        if len(self.prices) < self.period + 1:
            return None

        prices = list(self.prices)
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [max(c, 0.0) for c in changes]
        losses = [max(-c, 0.0) for c in changes]

        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    # ------------------------------------------------------------------
    # Strategy interface
    # ------------------------------------------------------------------

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        price = float(tick.get("price", 0.0))
        if price <= 0:
            return None

        self.prices.append(price)
        rsi = self._compute_rsi()
        if rsi is None:
            return None

        signal: Optional[str] = None

        if rsi <= self.oversold and self.current_position != "LONG":
            signal = "BUY"
            self.current_position = "LONG"
            logger.info(
                f"[{self.symbol}] RSI oversold: {rsi:.1f} ≤ {self.oversold} → BUY"
            )
        elif rsi >= self.overbought and self.current_position != "SHORT":
            signal = "SELL"
            self.current_position = "SHORT"
            logger.info(
                f"[{self.symbol}] RSI overbought: {rsi:.1f} ≥ {self.overbought} → SELL"
            )

        if signal is None:
            return None

        # Confidence = normalised distance past the threshold (clamped to [0.1, 1.0])
        if signal == "BUY":
            raw = (self.oversold - rsi) / self.oversold if self.oversold > 0 else 0.0
        else:
            range_ = 100.0 - self.overbought
            raw = (rsi - self.overbought) / range_ if range_ > 0 else 0.0
        confidence = round(max(0.1, min(raw, 1.0)), 3)

        return {
            "model_id": self.model_id,
            "model_name": "RSI_MeanReversion_v1",
            "symbol": self.symbol,
            "signal": signal,
            "confidence": confidence,
            "price": price,
            "explanation": [{"feature": "rsi", "value": round(rsi, 2)}],
            "timestamp": tick.get("timestamp"),
        }

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None
