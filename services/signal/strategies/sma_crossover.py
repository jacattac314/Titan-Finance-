from typing import Dict, Any, Optional, Deque
from collections import deque
import statistics
import logging
from .base import Strategy

logger = logging.getLogger("TitanSMACrossover")

class SMACrossover(Strategy):
    """
    Simple Moving Average Crossover Strategy.
    BUY when Fast SMA > Slow SMA (Golden Cross).
    SELL when Fast SMA < Slow SMA (Death Cross).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fast_period = config.get("fast_period", 20) # Ticks, not days ideally, but for MVP tick-based
        self.slow_period = config.get("slow_period", 50)
        
        # In a real system, we'd use a proper TimeSeries database or DataFrame window
        # For MVP, we use an in-memory deque of tick prices
        self.prices: Deque[float] = deque(maxlen=self.slow_period + 1)
        self.current_position = None # 'LONG', 'SHORT', or None

    async def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        price = float(tick.get("price", 0.0))
        if price <= 0:
            return None

        self.prices.append(price)
        
        # Need enough data
        if len(self.prices) < self.slow_period:
            return None

        # Calculate SMAs
        fast_sma = statistics.mean(list(self.prices)[-self.fast_period:])
        slow_sma = statistics.mean(list(self.prices)[-self.slow_period:])
        
        signal = None
        
        # Logic: Crossover
        if fast_sma > slow_sma and self.current_position != "LONG":
            signal = "BUY"
            self.current_position = "LONG"
            logger.info(f"[{self.symbol}] Golden Cross! Fast={fast_sma:.2f} > Slow={slow_sma:.2f}")
            
        elif fast_sma < slow_sma and self.current_position != "SHORT": # Or just close long?
            # For this simple bot, we reverse or close. Let's say we reverse to SHORT purely or just SELL to close.
            # Let's map SELL to "Exit Long" or "Enter Short"
            signal = "SELL"
            self.current_position = "SHORT"
            logger.info(f"[{self.symbol}] Death Cross! Fast={fast_sma:.2f} < Slow={slow_sma:.2f}")

        if signal:
            # 1-hour forecast: project price along fast SMA slope for 60 bars
            price_list = list(self.prices)
            if len(price_list) >= 2:
                # Calculate the per-bar drift from the fast SMA period
                recent_fast = price_list[-self.fast_period:]
                slope_per_bar = (recent_fast[-1] - recent_fast[0]) / max(len(recent_fast) - 1, 1)
                forecast_price = round(price + slope_per_bar * 60, 2)
            else:
                forecast_price = price
            
            current_ts = tick.get("timestamp", 0)
            forecast_timestamp = int(current_ts) + (60 * 60 * 1000)  # +1 hour in ms
            
            return {
                "model_id": self.model_id,
                "model_name": "SMA_Crossover_v1",
                "symbol": self.symbol,
                "signal": signal,
                "confidence": 1.0, # Simple logic has high mechanical confidence
                "price": price,
                "timestamp": current_ts,
                "forecast_price": forecast_price,
                "forecast_timestamp": forecast_timestamp
            }
            
        return None

    async def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Not using bars yet for this tick-based MVP
        return None
