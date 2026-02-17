import asyncio
import logging
import random

logger = logging.getLogger("TitanLatencySimulator")

class LatencySimulator:
    """
    Simulates network and processing delays to mimic real-world execution lag.
    """
    def __init__(self, min_ms: int = 50, max_ms: int = 200):
        self.min_ms = min_ms
        self.max_ms = max_ms

    async def delay(self):
        """Pause execution for a random duration."""
        ms = random.randint(self.min_ms, self.max_ms)
        await asyncio.sleep(ms / 1000.0)
        # logger.debug(f"Simulated Latency: {ms}ms")
