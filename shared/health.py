"""
TitanFlow Shared Health Server

Lightweight asyncio HTTP server exposing /healthz and /readyz endpoints.
Designed to run as a background task alongside the main service loop.

Usage:
    import asyncio
    from health import run_health_server

    async def main():
        health_task = asyncio.create_task(run_health_server(port=8080, service="my-service"))
        await asyncio.gather(health_task, run_my_service())
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Global readiness flag — set to True once the service is fully initialised.
_ready: bool = False
_start_time: str = datetime.datetime.now(datetime.timezone.utc).isoformat()


def set_ready(value: bool = True) -> None:
    """Mark the service as ready (or not ready) to serve traffic."""
    global _ready
    _ready = value


def is_ready() -> bool:
    return _ready


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
        body = json.dumps({
            "status": "ok",
            "service": service,
            "started_at": _start_time,
        })
        status = "200 OK"
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
