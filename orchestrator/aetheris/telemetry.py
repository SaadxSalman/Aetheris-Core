"""Per-request telemetry: async event bus consumed by the SSE endpoint.

Every agent node pushes structured events here; the API layer serializes them
as Server-Sent Events consumed by the React Flow visualizer on the frontend.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any

_SENTINEL = object()


class TelemetrySession:
    def __init__(self, request_id: str, max_events: int = 600, heartbeat: int = 10):
        self.request_id = request_id
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.history: deque[dict] = deque(maxlen=max_events)
        self.seq = 0
        self.started = time.time()
        self.heartbeat = heartbeat
        self.closed = False

    async def emit(self, event_type: str, payload: dict | None = None, node: str | None = None) -> None:
        if self.closed:
            return
        self.seq += 1
        event = {
            "type": event_type,
            "request_id": self.request_id,
            "seq": self.seq,
            "ts": round(time.time() * 1000, 3),
            "elapsed_ms": round((time.time() - self.started) * 1000, 2),
        }
        if node:
            event["node"] = node
        if payload:
            event["payload"] = payload
        self.history.append(event)
        self.queue.put_nowait(event)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.queue.put_nowait(_SENTINEL)

    async def stream(self):
        """Yield SSE-formatted strings until the sentinel arrives (with heartbeats)."""
        while True:
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=self.heartbeat)
            except asyncio.TimeoutError:
                yield ": ping\n\n"  # keep-alive comment
                continue
            if item is _SENTINEL:
                break
            yield _sse(item)
        # flush anything produced between last event and close
        while True:
            try:
                item = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is _SENTINEL:
                continue
            yield _sse(item)


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


# --------------------------------------------------------------------------- #
# Node lifecycle helper — wraps every agent node uniformly
# --------------------------------------------------------------------------- #
class NodeTrace:
    def __init__(self, session: TelemetrySession, node: str):
        self.session = session
        self.node = node
        self.t0 = 0.0

    async def __aenter__(self) -> "NodeTrace":
        self.t0 = time.time()
        await self.session.emit("node_start", {"node": self.node}, node=self.node)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        ms = round((time.time() - self.t0) * 1000, 2)
        if exc is not None:
            await self.session.emit(
                "node_end",
                {"node": self.node, "status": "error", "ms": ms, "error": str(exc)},
                node=self.node,
            )
            return False  # propagate
        await self.session.emit("node_end", {"node": self.node, "status": "ok", "ms": ms}, node=self.node)
        return False
