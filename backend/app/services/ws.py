"""Tiny WebSocket broadcast hub: dashboard clients subscribe to live events."""
from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    def broadcast(self, event: str, payload: dict | None = None) -> None:
        """Thread-safe fire-and-forget broadcast from sync code."""
        message = json.dumps({"event": event, "payload": payload or {}})
        loop = self.loop
        if loop is None or not self.clients:
            return

        async def _send() -> None:
            dead = []
            for ws in list(self.clients):
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(ws)

        asyncio.run_coroutine_threadsafe(_send(), loop)


hub = Hub()
