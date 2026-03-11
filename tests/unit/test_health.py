"""
Unit tests for shared/health.py

Covers:
  - /healthz returns 200 with status=ok when no liveness checks are registered.
  - /healthz returns 503 with status=degraded when a liveness check fails.
  - /healthz includes dependency results in the response body.
  - /readyz returns 200 when ready, 503 when not ready.
  - register_liveness_check callback is invoked on /healthz.
  - Timed-out liveness check is reported as degraded (not hung).
"""
import asyncio
import json
import pytest
import health as health_mod


# ---------------------------------------------------------------------------
# Helper: call _handle_request with a synthetic HTTP GET line
# ---------------------------------------------------------------------------

class _FakeWriter:
    def __init__(self):
        self._buf = bytearray()
        self.closed = False

    def write(self, data: bytes):
        self._buf.extend(data)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass

    @property
    def response_text(self) -> str:
        return self._buf.decode()

    @property
    def status_line(self) -> str:
        return self.response_text.split("\r\n")[0]

    @property
    def body(self) -> dict:
        body_start = self.response_text.index("\r\n\r\n") + 4
        return json.loads(self.response_text[body_start:])


async def fake_request(path: str, service: str = "test-svc") -> _FakeWriter:
    raw = f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode()
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    writer = _FakeWriter()
    await health_mod._handle_request(reader, writer, service)
    return writer


# ---------------------------------------------------------------------------
# /healthz — no liveness checks registered
# ---------------------------------------------------------------------------

class TestHealthzNoChecks:
    @pytest.fixture(autouse=True)
    def clear_checks(self):
        """Isolate tests by clearing the global liveness-check registry."""
        orig = health_mod._liveness_checks.copy()
        health_mod._liveness_checks.clear()
        yield
        health_mod._liveness_checks.clear()
        health_mod._liveness_checks.extend(orig)

    @pytest.mark.asyncio
    async def test_returns_200_ok(self):
        w = await fake_request("/healthz")
        assert "200 OK" in w.status_line

    @pytest.mark.asyncio
    async def test_body_status_ok(self):
        w = await fake_request("/healthz")
        assert w.body["status"] == "ok"

    @pytest.mark.asyncio
    async def test_body_contains_service(self):
        w = await fake_request("/healthz", service="titan-risk")
        assert w.body["service"] == "titan-risk"

    @pytest.mark.asyncio
    async def test_no_dependencies_key_when_no_checks(self):
        w = await fake_request("/healthz")
        assert "dependencies" not in w.body


# ---------------------------------------------------------------------------
# /healthz — with liveness checks
# ---------------------------------------------------------------------------

class TestHealthzWithChecks:
    @pytest.fixture(autouse=True)
    def clear_checks(self):
        orig = health_mod._liveness_checks.copy()
        health_mod._liveness_checks.clear()
        yield
        health_mod._liveness_checks.clear()
        health_mod._liveness_checks.extend(orig)

    @pytest.mark.asyncio
    async def test_200_when_all_checks_pass(self):
        async def check_redis():
            return True, None

        health_mod.register_liveness_check(check_redis)
        w = await fake_request("/healthz")
        assert "200 OK" in w.status_line
        assert w.body["status"] == "ok"
        assert w.body["dependencies"]["check_redis"]["ok"] is True

    @pytest.mark.asyncio
    async def test_503_when_check_fails(self):
        async def check_db():
            return False, "connection refused"

        health_mod.register_liveness_check(check_db)
        w = await fake_request("/healthz")
        assert "503" in w.status_line
        assert w.body["status"] == "degraded"
        dep = w.body["dependencies"]["check_db"]
        assert dep["ok"] is False
        assert dep["detail"] == "connection refused"

    @pytest.mark.asyncio
    async def test_503_when_check_times_out(self):
        async def check_slow():
            await asyncio.sleep(10)  # will time out inside _run_liveness_checks
            return True, None

        health_mod.register_liveness_check(check_slow)
        w = await fake_request("/healthz")
        assert "503" in w.status_line
        assert w.body["status"] == "degraded"
        dep = w.body["dependencies"]["check_slow"]
        assert dep["ok"] is False
        assert dep["detail"] == "timeout"

    @pytest.mark.asyncio
    async def test_partial_failure_is_degraded(self):
        async def check_ok():
            return True, None

        async def check_fail():
            return False, "down"

        health_mod.register_liveness_check(check_ok)
        health_mod.register_liveness_check(check_fail)
        w = await fake_request("/healthz")
        assert w.body["status"] == "degraded"
        assert w.body["dependencies"]["check_ok"]["ok"] is True
        assert w.body["dependencies"]["check_fail"]["ok"] is False


# ---------------------------------------------------------------------------
# /readyz
# ---------------------------------------------------------------------------

class TestReadyz:
    @pytest.fixture(autouse=True)
    def reset_ready(self):
        orig = health_mod._ready
        yield
        health_mod._ready = orig

    @pytest.mark.asyncio
    async def test_200_when_ready(self):
        health_mod.set_ready(True)
        w = await fake_request("/readyz")
        assert "200 OK" in w.status_line
        assert w.body["status"] == "ready"

    @pytest.mark.asyncio
    async def test_503_when_not_ready(self):
        health_mod.set_ready(False)
        w = await fake_request("/readyz")
        assert "503" in w.status_line
        assert w.body["status"] == "not_ready"


# ---------------------------------------------------------------------------
# Unknown path
# ---------------------------------------------------------------------------

class TestUnknownPath:
    @pytest.mark.asyncio
    async def test_404_for_unknown_path(self):
        w = await fake_request("/unknown")
        assert "404" in w.status_line
