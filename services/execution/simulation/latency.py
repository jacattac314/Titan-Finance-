import asyncio
import logging
import random
import math

logger = logging.getLogger("TitanLatencySimulator")

class LatencySimulator:
    """
    Simulates network and processing delays to mimic real-world execution lag.
    """
    def __init__(self, min_ms: int = 50, max_ms: int = 200):
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.mu = math.log((min_ms + max_ms) / 2)
        self.sigma = 0.5 

    async def delay(self):
        """Pause execution for a random, realistic duration (Lognormal)."""
        ms = random.lognormvariate(self.mu, self.sigma)
        # Ensure we don't go below the absolute physical minimum (e.g. 5ms fiber)
        ms = max(5.0, min(ms, 2000.0))  
        await asyncio.sleep(ms / 1000.0)
        # logger.debug(f"Simulated Latency: {ms:.1f}ms")
