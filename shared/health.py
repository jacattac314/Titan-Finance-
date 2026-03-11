"""
TitanFlow Shared Health Server

Lightweight asyncio HTTP server exposing /healthz and /readyz endpoints.
Designed to run as a background task alongside the main service loop.

Usage:
    import asyncio
    from health import run_health_server, register_liveness_check, set_ready

    async def check_redis():
        try:
            await redis_client.ping()
            return True, None
        except Exception as exc:
            return False, str(exc)

    async def main():
        register_liveness_check(check_redis)
        health_task = asyncio.create_task(run_health_server(port=8080, service="my-service"))
        await asyncio.gather(health_task, run_my_service())
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from typing import Awaitable, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Global readiness flag — set to True once the service is fully initialised.
_ready: bool = False
_start_time: str = datetime.datetime.now(datetime.timezone.utc).isoformat()

# Optional async callables that return (ok: bool, detail: str | None).
# Registered by services to surface dependency health via /healthz.
_liveness_checks: List[Callable[[], Awaitable[Tuple[bool, Optional[str]]]]] = []


def set_ready(value: bool = True) -> None:
    """Mark the service as ready (or not ready) to serve traffic."""
    global _ready
    _ready = value


def is_ready() -> bool:
    return _ready


def register_liveness_check(
    fn: Callable[[], Awaitable[Tuple[bool, Optional[str]]]],
) -> None:
    """Register an async dependency check for the /healthz endpoint.

    The callable must return a ``(ok, detail)`` tuple where *ok* is ``True``
    when the dependency is healthy and *detail* is an optional error string.

    Example::

        async def _check_redis() -> tuple[bool, str | None]:
            try:
                await redis_client.ping()
                return True, None
            except Exception as exc:
                return False, str(exc)

        register_liveness_check(_check_redis)
    """
    _liveness_checks.append(fn)


async def _run_liveness_checks() -> Tuple[bool, dict]:
    """Run all registered liveness checks and return (all_ok, results_dict)."""
    results = {}
    all_ok = True
    for fn in _liveness_checks:
        name = fn.__name__.lstrip("_")
        try:
            ok, detail = await asyncio.wait_for(fn(), timeout=2.0)
        except asyncio.TimeoutError:
            ok, detail = False, "timeout"
        except Exception as exc:
            ok, detail = False, str(exc)
        results[name] = {"ok": ok, **({"detail": detail} if detail else {})}
        if not ok:
            all_ok = False
    return all_ok, results


async def _handle_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    service: str,
) -> None:
    try:
        raw = await asyncio.wait_for(reader.read(1024), timeout=2.0)
    except asyncio.TimeoutError:
        writer.close()
        return

    request_line = raw.decode(errors="replace").split("\r\n")[0]
    parts = request_line.split(" ")
    path = parts[1] if len(parts) >= 2 else "/"

    if path == "/healthz":
        deps_ok, dep_results = await _run_liveness_checks()
        body = json.dumps({
            "status": "ok" if deps_ok else "degraded",
            "service": service,
            "started_at": _start_time,
            **({"dependencies": dep_results} if dep_results else {}),
        })
        status = "200 OK" if deps_ok else "503 Service Unavailable"

    elif path == "/readyz":
        if _ready:
            body = json.dumps({"status": "ready", "service": service})
            status = "200 OK"
        else:
            body = json.dumps({"status": "not_ready", "service": service})
            status = "503 Service Unavailable"

    else:
        body = json.dumps({"error": "not found"})
        status = "404 Not Found"

    response = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
        f"{body}"
    )
    writer.write(response.encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def run_health_server(
    port: Optional[int] = None,
    service: str = "titan-service",
) -> None:
    """Start the health HTTP server and serve forever.

    Reads HEALTH_PORT env var if *port* is not provided (default: 8080).
    """
    port = port or int(os.getenv("HEALTH_PORT", "8080"))

    async def handler(reader, writer):
        await _handle_request(reader, writer, service)

    server = await asyncio.start_server(handler, "0.0.0.0", port)
    logger.info("Health server listening on :%d (/healthz, /readyz)", port)
    async with server:
        await server.serve_forever()
