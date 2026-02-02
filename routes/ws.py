"""WebSocket handlers — /ws/state (observer) and /ws/feedback (operator)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)


class FeedbackBroadcaster:
    """Manages operator feedback WebSocket connections."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    def broadcast(self, event: dict) -> None:
        """Non-async broadcast — schedules sends on the event loop."""
        for ws in list(self._connections):
            try:
                asyncio.get_event_loop().create_task(ws.send_json(event))
            except Exception:
                self._connections.remove(ws)


def create_router(state_agg, feedback_broadcaster: FeedbackBroadcaster, config):
    @router.websocket("/ws/state")
    async def ws_state(ws: WebSocket):
        await ws.accept()
        interval = 1.0 / config.observer_state_hz
        try:
            while True:
                await ws.send_json(state_agg.state)
                await asyncio.sleep(interval)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("ws/state error")

    @router.websocket("/ws/feedback")
    async def ws_feedback(ws: WebSocket):
        await feedback_broadcaster.connect(ws)
        try:
            while True:
                # Keep connection alive; client doesn't need to send anything
                await ws.receive_text()
        except WebSocketDisconnect:
            feedback_broadcaster.disconnect(ws)
        except Exception:
            feedback_broadcaster.disconnect(ws)

    return router
