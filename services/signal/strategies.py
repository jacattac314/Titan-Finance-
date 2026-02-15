from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd
import ta


@dataclass
class StrategyDecision:
    signal: str
    confidence: float
    explanation: List[dict]


class Strategy(ABC):
    """Base interface for baseline contenders in the paper-trading arena."""

    model_id: str = "strategy"
    model_name: str = "Strategy"

    @abstractmethod
    def generate_signal(self, bars: list[dict]) -> StrategyDecision | None:
        """Return BUY/SELL decision or None when no action is needed."""
        raise NotImplementedError


class SMACrossover(Strategy):
    model_id = "sma_crossover"
    model_name = "SMA Crossover"

    def __init__(
        self,
        short_window: int = 10,
        long_window: int = 30,
        min_spread_pct: float = 0.001,
    ):
        if short_window >= long_window:
            raise ValueError("short_window must be less than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.min_spread_pct = min_spread_pct

    def generate_signal(self, bars: list[dict]) -> StrategyDecision | None:
        if len(bars) < (self.long_window + 1):
            return None

        closes = pd.Series([float(row["close"]) for row in bars], dtype=float)
        short_sma = closes.rolling(self.short_window).mean()
        long_sma = closes.rolling(self.long_window).mean()
        if pd.isna(short_sma.iloc[-1]) or pd.isna(long_sma.iloc[-1]):
            return None

        short_prev = float(short_sma.iloc[-2])
        long_prev = float(long_sma.iloc[-2])
        short_curr = float(short_sma.iloc[-1])
        long_curr = float(long_sma.iloc[-1])
        if long_curr == 0:
            return None

        spread_pct = (short_curr - long_curr) / long_curr
        crossed_up = short_prev <= long_prev and short_curr > long_curr
        crossed_down = short_prev >= long_prev and short_curr < long_curr

        if not crossed_up and not crossed_down:
            return None
        if abs(spread_pct) < self.min_spread_pct:
            return None

        confidence = min(abs(spread_pct) / 0.02, 1.0)
        explanation = [
            {"feature": "sma_short", "impact": short_curr},
            {"feature": "sma_long", "impact": long_curr},
            {"feature": "sma_spread_pct", "impact": spread_pct},
        ]
        signal = "BUY" if crossed_up else "SELL"
        return StrategyDecision(signal=signal, confidence=float(confidence), explanation=explanation)


class RSIMeanReversion(Strategy):
    model_id = "rsi_mean_reversion"
    model_name = "RSI Mean Reversion"

    def __init__(
        self,
        window: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ):
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, bars: list[dict]) -> StrategyDecision | None:
        if len(bars) < (self.window + 2):
            return None

        closes = pd.Series([float(row["close"]) for row in bars], dtype=float)
        rsi = ta.momentum.RSIIndicator(close=closes, window=self.window).rsi()
        if rsi.isna().iloc[-1]:
            return None

        rsi_curr = float(rsi.iloc[-1])
        rsi_prev = float(rsi.iloc[-2]) if not np.isnan(rsi.iloc[-2]) else rsi_curr

        if rsi_curr <= self.oversold:
            pressure = (self.oversold - rsi_curr) / max(self.oversold, 1.0)
            confidence = min(max(pressure, 0.2), 1.0)
            explanation = [
                {"feature": "rsi_value", "impact": rsi_curr},
                {"feature": "rsi_rebound", "impact": rsi_curr - rsi_prev},
            ]
            return StrategyDecision("BUY", float(confidence), explanation)

        if rsi_curr >= self.overbought:
            pressure = (rsi_curr - self.overbought) / max(100.0 - self.overbought, 1.0)
            confidence = min(max(pressure, 0.2), 1.0)
            explanation = [
                {"feature": "rsi_value", "impact": rsi_curr},
                {"feature": "rsi_cooldown", "impact": rsi_prev - rsi_curr},
            ]
            return StrategyDecision("SELL", float(confidence), explanation)

        return None
