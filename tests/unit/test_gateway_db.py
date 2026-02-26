"""
Unit tests for services/gateway/db.py (DatabaseManager)

DatabaseManager is the gateway's I/O backbone: it writes ticks to QuestDB
via UDP line-protocol, publishes them to Redis for real-time consumers, and
exposes a price-cache read path.  All network calls are replaced with mocks
so the suite runs without any live infrastructure.
"""
import importlib.util
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Stub heavy dependencies that may not be installed in all environments.
# This must happen before the module is loaded so that the module-level
# `import asyncpg` and `import redis.asyncio` succeed.
# ---------------------------------------------------------------------------

for _dep in ("asyncpg", "redis", "redis.asyncio"):
    if _dep not in sys.modules:
        sys.modules[_dep] = MagicMock()

# ---------------------------------------------------------------------------
# Module loader — avoids the name collision with services/signal/db.py since
# both files are named 'db.py'.  Loading by absolute path gives each module
# a unique entry in sys.modules.
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_module():
    path = os.path.join(_REPO_ROOT, "services/gateway/db.py")
    spec = importlib.util.spec_from_file_location("gateway_db", path)
    mod = importlib.util.module_from_spec(spec)
    with patch("socket.socket"):          # prevent real UDP socket on import
        spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
DatabaseManager = _mod.DatabaseManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db() -> DatabaseManager:
    """Fresh DatabaseManager with a mock socket."""
    with patch("socket.socket"):
        db = DatabaseManager()
    db.sock = MagicMock()
    return db


def make_redis_mock():
    m = AsyncMock()
    m.ping = AsyncMock()
    m.publish = AsyncMock()
    m.set = AsyncMock()
    m.get = AsyncMock()
    m.close = AsyncMock()
    return m


def make_pool_mock():
    pool = AsyncMock()
    pool.close = AsyncMock()
    return pool


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------

class TestConnect:
    async def test_success_sets_pg_pool_and_redis(self):
        db = make_db()
        mock_pool = make_pool_mock()
        mock_redis = make_redis_mock()

        with patch.object(_mod, "asyncpg") as mock_asyncpg, \
             patch.object(_mod, "redis") as mock_redis_mod:
            mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
            mock_redis_mod.from_url = MagicMock(return_value=mock_redis)

            await db.connect()

        assert db.pg_pool is mock_pool
        assert db.redis is mock_redis

    async def test_asyncpg_failure_propagates(self):
        db = make_db()
        with patch.object(_mod, "asyncpg") as mock_asyncpg:
            mock_asyncpg.create_pool = AsyncMock(
                side_effect=ConnectionRefusedError("postgres unavailable")
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
    async def test_closes_pg_pool_redis_and_sock(self):
        db = make_db()
        db.pg_pool = make_pool_mock()
        db.redis = make_redis_mock()

        await db.close()

        db.pg_pool.close.assert_awaited_once()
        db.redis.close.assert_awaited_once()
        db.sock.close.assert_called_once()

    async def test_no_error_when_connections_are_none(self):
        db = make_db()
        db.pg_pool = None
        db.redis = None
        # Must not raise — close() is called during shutdown regardless of
        # whether connect() ever succeeded.
        await db.close()
        db.sock.close.assert_called_once()


# ---------------------------------------------------------------------------
# write_tick()
# ---------------------------------------------------------------------------

class TestWriteTick:
    def test_sends_influx_line_protocol_to_questdb(self):
        db = make_db()
        db.write_tick("AAPL", 175.50, 100, 1_700_000_000_000_000_000)

        db.sock.sendto.assert_called_once()
        payload = db.sock.sendto.call_args[0][0].decode()

        assert "market_data,symbol=AAPL" in payload
        assert "price=175.5" in payload
        assert "size=100i" in payload
        assert "1700000000000000000" in payload

    def test_destination_is_configured_questdb_host_and_port(self):
        db = make_db()
        db.quest_host = "questdb-host"
        db.quest_port = 9009
        db.write_tick("AAPL", 100.0, 1, 0)

        dest = db.sock.sendto.call_args[0][1]
        assert dest == ("questdb-host", 9009)

    def test_socket_error_does_not_propagate(self):
        db = make_db()
        db.sock.sendto.side_effect = OSError("network down")
        # Gateway must not crash on a failed tick write — log and continue.
        db.write_tick("AAPL", 175.50, 100, 1_700_000_000_000_000_000)


# ---------------------------------------------------------------------------
# publish_tick()
# ---------------------------------------------------------------------------

class TestPublishTick:
    async def test_publishes_json_to_market_data_channel(self):
        db = make_db()
        db.redis = make_redis_mock()

        await db.publish_tick("BTCUSD", 45000.0, 1, 1_700_000_000_000_000_000)

        db.redis.publish.assert_awaited_once()
        channel, raw = db.redis.publish.call_args[0]
        assert channel == "market_data"
        msg = json.loads(raw)
        assert msg["symbol"] == "BTCUSD"
        assert msg["price"] == 45000.0
        assert msg["size"] == 1
        assert msg["type"] == "trade"
        assert msg["timestamp"] == 1_700_000_000_000_000_000

    async def test_sets_price_key_in_redis_cache(self):
        db = make_db()
        db.redis = make_redis_mock()

        await db.publish_tick("BTCUSD", 45000.0, 1, 0)

        db.redis.set.assert_awaited_once_with("price:BTCUSD", "45000.0")

    async def test_noop_when_redis_is_none(self):
        db = make_db()
        db.redis = None
        # Must not raise.
        await db.publish_tick("BTCUSD", 45000.0, 1, 0)

    async def test_redis_error_does_not_propagate(self):
        db = make_db()
        db.redis = make_redis_mock()
        db.redis.publish = AsyncMock(side_effect=RuntimeError("redis down"))
        # Non-fatal — gateway must keep running even if publish fails.
        await db.publish_tick("BTCUSD", 45000.0, 1, 0)


# ---------------------------------------------------------------------------
# get_latest_price()
# ---------------------------------------------------------------------------

class TestGetLatestPrice:
    async def test_returns_float_when_key_exists(self):
        db = make_db()
        db.redis = make_redis_mock()
        db.redis.get = AsyncMock(return_value=b"45123.75")

        result = await db.get_latest_price("BTCUSD")

        assert result == pytest.approx(45123.75)

    async def test_returns_none_when_key_is_missing(self):
        db = make_db()
        db.redis = make_redis_mock()
        db.redis.get = AsyncMock(return_value=None)

        result = await db.get_latest_price("UNKNOWN")

        assert result is None

    async def test_returns_none_when_redis_is_none(self):
        db = make_db()
        db.redis = None

        result = await db.get_latest_price("BTCUSD")

        assert result is None

    async def test_returns_none_on_redis_error(self):
        db = make_db()
        db.redis = make_redis_mock()
        db.redis.get = AsyncMock(side_effect=RuntimeError("connection lost"))

        result = await db.get_latest_price("BTCUSD")

        assert result is None
