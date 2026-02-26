"""
Unit tests for services/signal/db.py (SignalDB)

SignalDB connects the signal service to QuestDB (for OHLCV history) and
Redis (for publishing trade signals).  Tests cover the connection lifecycle,
OHLCV aggregation query, chronological ordering of results, and the signal
publish path.  All network calls are replaced with mocks so the suite runs
without any live infrastructure.
"""
import importlib.util
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Stub heavy dependencies that may not be installed in all environments.
# Must happen before the module is loaded so that module-level imports succeed.
# ---------------------------------------------------------------------------

for _dep in ("asyncpg", "redis", "redis.asyncio"):
    if _dep not in sys.modules:
        sys.modules[_dep] = MagicMock()

# ---------------------------------------------------------------------------
# Module loader — loads signal/db.py by absolute path to avoid the 'db'
# name collision with gateway/db.py (both live at the top level of their
# respective service directories and are added to sys.path by conftest.py).
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_module():
    path = os.path.join(_REPO_ROOT, "services/signal/db.py")
    spec = importlib.util.spec_from_file_location("signal_db", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
SignalDB = _mod.SignalDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db() -> SignalDB:
    return SignalDB()


def make_redis_mock():
    m = AsyncMock()
    m.ping = AsyncMock()
    m.publish = AsyncMock()
    m.close = AsyncMock()
    return m


def make_pool_mock():
    pool = AsyncMock()
    pool.close = AsyncMock()
    return pool


def make_acquire_cm(rows):
    """Async context manager that yields a connection whose fetch() returns *rows*."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=rows)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, mock_conn


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------

class TestConnect:
    async def test_success_sets_quest_pool_and_redis(self):
        db = make_db()
        mock_pool = make_pool_mock()
        mock_redis = make_redis_mock()

        with patch.object(_mod, "asyncpg") as mock_asyncpg, \
             patch.object(_mod, "redis") as mock_redis_mod:
            mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
            mock_redis_mod.from_url = MagicMock(return_value=mock_redis)

            await db.connect()

        assert db.quest_pool is mock_pool
        assert db.redis is mock_redis

    async def test_asyncpg_failure_propagates(self):
        db = make_db()
        with patch.object(_mod, "asyncpg") as mock_asyncpg:
            mock_asyncpg.create_pool = AsyncMock(
                side_effect=ConnectionRefusedError("questdb unavailable")
            )
            with pytest.raises(ConnectionRefusedError):
                await db.connect()

    async def test_redis_ping_failure_propagates(self):
        db = make_db()
        mock_pool = make_pool_mock()
        mock_redis = make_redis_mock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionRefusedError("redis unavailable"))

        with patch.object(_mod, "asyncpg") as mock_asyncpg, \
             patch.object(_mod, "redis") as mock_redis_mod:
            mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
            mock_redis_mod.from_url = MagicMock(return_value=mock_redis)

            with pytest.raises(ConnectionRefusedError):
                await db.connect()


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------

class TestClose:
    async def test_closes_quest_pool_and_redis(self):
        db = make_db()
        db.quest_pool = make_pool_mock()
        db.redis = make_redis_mock()

        await db.close()

        db.quest_pool.close.assert_awaited_once()
        db.redis.close.assert_awaited_once()

    async def test_no_error_when_connections_are_none(self):
        db = make_db()
        db.quest_pool = None
        db.redis = None
        # Must not raise — called during startup failure before connect() succeeds.
        await db.close()


# ---------------------------------------------------------------------------
# fetch_ohlcv()
# ---------------------------------------------------------------------------

class TestFetchOhlcv:
    async def test_returns_empty_list_when_pool_is_none(self):
        db = make_db()
        db.quest_pool = None

        result = await db.fetch_ohlcv("AAPL")

        assert result == []

    async def test_returns_chronological_bars(self):
        db = make_db()
        # QuestDB returns rows DESC (newest first); fetch_ohlcv must reverse them.
        raw_rows = [
            {"timestamp": 3, "open": 103.0, "high": 105.0, "low": 101.0, "close": 104.0, "volume": 300},
            {"timestamp": 2, "open": 102.0, "high": 104.0, "low": 100.0, "close": 103.0, "volume": 200},
            {"timestamp": 1, "open": 101.0, "high": 103.0, "low":  99.0, "close": 102.0, "volume": 100},
        ]
        cm, _ = make_acquire_cm(raw_rows)
        pool = make_pool_mock()
        pool.acquire = MagicMock(return_value=cm)
        db.quest_pool = pool

        result = await db.fetch_ohlcv("AAPL", limit=3)

        assert len(result) == 3
        assert result[0]["timestamp"] == 1   # oldest first
        assert result[-1]["timestamp"] == 3  # newest last

    async def test_passes_symbol_and_limit_into_query(self):
        db = make_db()
        cm, mock_conn = make_acquire_cm([])
        pool = make_pool_mock()
        pool.acquire = MagicMock(return_value=cm)
        db.quest_pool = pool

        await db.fetch_ohlcv("TSLA", limit=42)

        query = mock_conn.fetch.call_args[0][0]
        assert "TSLA" in query
        assert "42" in query

    async def test_returns_empty_list_on_query_error(self):
        db = make_db()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=RuntimeError("questdb query failed"))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        pool = make_pool_mock()
        pool.acquire = MagicMock(return_value=cm)
        db.quest_pool = pool

        result = await db.fetch_ohlcv("AAPL")

        # Signal service must degrade gracefully — an empty bar list causes
        # the strategy to skip the tick rather than crash.
        assert result == []

    async def test_each_row_converted_to_dict(self):
        db = make_db()
        # asyncpg returns Record objects; dict(row) must work on whatever fetch returns.
        # Use plain dicts here (dict(d) == d), verifying the conversion path is exercised.
        raw_rows = [{"timestamp": 1, "open": 100.0, "high": 101.0, "low": 99.0,
                     "close": 100.5, "volume": 50}]
        cm, _ = make_acquire_cm(raw_rows)
        pool = make_pool_mock()
        pool.acquire = MagicMock(return_value=cm)
        db.quest_pool = pool

        result = await db.fetch_ohlcv("SPY", limit=1)

        assert isinstance(result[0], dict)
        assert result[0]["close"] == 100.5


# ---------------------------------------------------------------------------
# publish_signal()
# ---------------------------------------------------------------------------

class TestPublishSignal:
    async def test_publishes_json_to_trade_signals_channel(self):
        db = make_db()
        db.redis = make_redis_mock()
        payload = {"symbol": "AAPL", "signal": "BUY", "model_id": "lgbm", "confidence": 0.87}

        await db.publish_signal(payload)

        db.redis.publish.assert_awaited_once()
        channel, raw = db.redis.publish.call_args[0]
        assert channel == "trade_signals"
        assert json.loads(raw) == payload

    async def test_noop_when_redis_is_none(self):
        db = make_db()
        db.redis = None
        # Must not raise.
        await db.publish_signal({"symbol": "AAPL", "signal": "BUY", "model_id": "lgbm"})

    async def test_redis_error_does_not_propagate(self):
        db = make_db()
        db.redis = make_redis_mock()
        db.redis.publish = AsyncMock(side_effect=RuntimeError("redis down"))
        # Non-fatal — signal service must keep running even if publish fails.
        await db.publish_signal({"symbol": "AAPL", "signal": "BUY", "model_id": "lgbm"})
