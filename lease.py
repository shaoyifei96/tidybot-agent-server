"""Lease manager — queue, acquire, release, idle detection."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from config import LeaseConfig

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    lease_id: str
    holder: str  # client identifier
    granted_at: float
    last_cmd_at: float
    warned: bool = False


@dataclass
class QueueEntry:
    holder: str
    future: asyncio.Future


class LeaseManager:
    """Manages operator lease with idle detection and queue."""

    def __init__(
        self,
        config: LeaseConfig,
        motors_moving_fn: Callable[[], bool],
        on_lease_event: Callable[[dict], None] | None = None,
    ) -> None:
        self._cfg = config
        self._motors_moving = motors_moving_fn
        self._on_event = on_lease_event or (lambda e: None)
        self._current: Lease | None = None
        self._queue: deque[QueueEntry] = deque()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def current_lease(self) -> Lease | None:
        return self._current

    async def start(self) -> None:
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def acquire(self, holder: str) -> dict:
        async with self._lock:
            if self._current is None:
                return self._grant(holder)
            # Already holder?
            if self._current.holder == holder:
                return {
                    "status": "already_held",
                    "lease_id": self._current.lease_id,
                    "remaining_s": self._remaining(),
                }
            # Queue
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            entry = QueueEntry(holder=holder, future=fut)
            self._queue.append(entry)
            position = len(self._queue)

        # Wait outside lock
        result = await fut
        return result

    async def release(self, lease_id: str) -> dict:
        async with self._lock:
            if self._current and self._current.lease_id == lease_id:
                self._current = None
                self._try_grant_next()
                return {"status": "released"}
            return {"status": "not_found"}

    async def extend(self, lease_id: str) -> dict:
        async with self._lock:
            if self._current and self._current.lease_id == lease_id:
                self._current.last_cmd_at = time.time()
                self._current.warned = False
                return {"status": "extended", "remaining_s": self._remaining()}
            return {"status": "not_found"}

    def record_command(self) -> None:
        """Called when operator sends a command."""
        if self._current:
            self._current.last_cmd_at = time.time()
            self._current.warned = False

    def validate_lease(self, lease_id: str) -> bool:
        return self._current is not None and self._current.lease_id == lease_id

    def status(self) -> dict:
        if self._current is None:
            return {"holder": None, "queue_length": len(self._queue)}
        return {
            "holder": self._current.holder,
            "lease_id": self._current.lease_id,
            "remaining_s": self._remaining(),
            "queue_length": len(self._queue),
        }

    # -- internals -----------------------------------------------------------

    def _grant(self, holder: str) -> dict:
        now = time.time()
        lease = Lease(
            lease_id=str(uuid.uuid4()),
            holder=holder,
            granted_at=now,
            last_cmd_at=now,
        )
        self._current = lease
        event = {
            "type": "lease_granted",
            "lease_id": lease.lease_id,
            "max_duration_s": self._cfg.max_duration_s,
        }
        self._on_event(event)
        logger.info("Lease granted to %s (%s)", holder, lease.lease_id)
        return {"status": "granted", **event}

    def _remaining(self) -> float:
        if not self._current:
            return 0.0
        elapsed = time.time() - self._current.granted_at
        return max(0.0, self._cfg.max_duration_s - elapsed)

    def _try_grant_next(self) -> None:
        while self._queue:
            entry = self._queue.popleft()
            if not entry.future.done():
                result = self._grant(entry.holder)
                entry.future.set_result(result)
                return

    def _revoke(self, reason: str) -> None:
        if not self._current:
            return
        event = {"type": "lease_revoked", "reason": reason}
        self._on_event(event)
        logger.info("Lease revoked from %s: %s", self._current.holder, reason)
        self._current = None
        self._try_grant_next()

    async def _check_loop(self) -> None:
        while True:
            await asyncio.sleep(self._cfg.check_interval_s)
            async with self._lock:
                if not self._current:
                    continue
                now = time.time()

                # Hard max duration
                if now - self._current.granted_at >= self._cfg.max_duration_s:
                    self._revoke("max_duration")
                    continue

                # Idle check
                idle_s = now - self._current.last_cmd_at
                is_active = self._motors_moving()

                if idle_s >= self._cfg.idle_timeout_s and not is_active:
                    if not self._current.warned:
                        self._current.warned = True
                        self._on_event({
                            "type": "lease_warning",
                            "reason": "idle",
                            "seconds_remaining": self._cfg.warning_grace_s,
                        })
                    elif idle_s >= self._cfg.idle_timeout_s + self._cfg.warning_grace_s:
                        self._revoke("idle_timeout")
