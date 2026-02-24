"""
Unit tests for services/execution/simulation/latency.py

LatencySimulator introduces randomised async delays to mimic real-world
network and processing lag.  Tests verify the statistical bounds of the
delay and that the coroutine contract is upheld.
"""
import asyncio
import time
import pytest
from simulation.latency import LatencySimulator


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_default_bounds(self):
        ls = LatencySimulator()
        assert ls.min_ms == 50
        assert ls.max_ms == 200

    def test_custom_bounds(self):
        ls = LatencySimulator(min_ms=10, max_ms=30)
        assert ls.min_ms == 10
        assert ls.max_ms == 30


# ---------------------------------------------------------------------------
# delay() — timing bounds
# ---------------------------------------------------------------------------

class TestDelay:
    def test_delay_completes_without_error(self):
        ls = LatencySimulator(min_ms=1, max_ms=5)
        run(ls.delay())  # must not raise

    def test_delay_is_coroutine(self):
        ls = LatencySimulator(min_ms=1, max_ms=5)
        import inspect
        assert inspect.iscoroutinefunction(ls.delay)

    def test_delay_duration_within_bounds(self):
        ls = LatencySimulator(min_ms=10, max_ms=50)
        start = time.monotonic()
        run(ls.delay())
        elapsed_ms = (time.monotonic() - start) * 1000
        # Allow generous upper margin for OS scheduling jitter
        assert elapsed_ms >= 9          # at least min_ms (9ms tolerance)
        assert elapsed_ms <= 200        # well under max_ms + overhead

    def test_equal_min_max_gives_fixed_delay(self):
        ls = LatencySimulator(min_ms=20, max_ms=20)
        start = time.monotonic()
        run(ls.delay())
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms >= 15         # at least 20ms (5ms tolerance)
        assert elapsed_ms < 100         # not unreasonably slow
