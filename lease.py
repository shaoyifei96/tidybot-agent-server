"""Lease manager — queue, acquire, release, idle detection."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Awaitable

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
        last_moved_at_fn: Callable[[], float],
        on_lease_event: Callable[[dict], None] | None = None,
    ) -> None:
        self._cfg = config
        self._last_moved_at = last_moved_at_fn
        self._on_event = on_lease_event or (lambda e: None)
        self._current: Lease | None = None
        self._queue: deque[QueueEntry] = deque()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._paused: bool = False

        # Reset-on-release state
        self._resetting: bool = False
        self._reset_task: asyncio.Task | None = None
        self._on_lease_end_async: Callable[[], Awaitable[None]] | None = None
        self._on_lease_start: Callable[[], None] | None = None

    @property
    def current_lease(self) -> Lease | None:
        return self._current

    def set_on_lease_end(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Set async callback invoked when a lease ends (rewind + clear)."""
        self._on_lease_end_async = callback

    def set_on_lease_start(self, callback: Callable[[str], None]) -> None:
        """Set callback invoked when a lease is granted.

        Args:
            callback: Called with the holder name as argument.
        """
        self._on_lease_start = callback

    async def start(self) -> None:
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self) -> None:
        if self._reset_task and not self._reset_task.done():
            self._reset_task.cancel()
            try:
                await self._reset_task
            except asyncio.CancelledError:
                pass
            self._resetting = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def acquire(self, holder: str) -> dict:
        async with self._lock:
            if self._current is None and not self._resetting and not self._paused:
                return self._grant(holder)
            # Already holder?
            if self._current and self._current.holder == holder:
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
                holder = self._current.holder
                self._current = None
                if self._cfg.reset_on_release and self._on_lease_end_async:
                    self._resetting = True
                    self._reset_task = asyncio.create_task(
                        self._do_reset_and_grant(reason="released")
                    )
                    return {"status": "released", "resetting": True}
                else:
                    self._try_grant_next()
                    return {"status": "released", "resetting": False}
            return {"status": "not_found"}

    async def extend(self, lease_id: str) -> dict:
        async with self._lock:
            if self._current and self._current.lease_id == lease_id:
                self._current.last_cmd_at = time.time()
                self._current.warned = False
                return {"status": "extended", "remaining_s": self._remaining()}
            return {"status": "not_found"}

    async def clear_queue(self) -> dict:
        """Clear queue, revoke current lease, stop code, and trigger rewind."""
        async with self._lock:
            # Clear queued entries first so _try_grant_next finds nothing
            removed = 0
            while self._queue:
                entry = self._queue.popleft()
                if not entry.future.done():
                    entry.future.cancel()
                removed += 1

            had_lease = self._current is not None
            if had_lease:
                self._revoke("queue_cleared")

            logger.info("Cleared queue (%d removed), revoked lease: %s",
                         removed, had_lease)
            return {
                "status": "cleared",
                "removed": removed,
                "lease_revoked": had_lease,
                "resetting": self._resetting,
            }

    def record_command(self) -> None:
        """Called when operator sends a command."""
        if self._current:
            self._current.last_cmd_at = time.time()
            self._current.warned = False

    def validate_lease(self, lease_id: str) -> bool:
        return self._current is not None and self._current.lease_id == lease_id

    def status(self) -> dict:
        # Build queue list (only holder names, not futures)
        queue_list = [{"position": i + 1, "holder": entry.holder}
                      for i, entry in enumerate(self._queue)]

        config = {
            "max_duration_s": self._cfg.max_duration_s,
            "idle_timeout_s": self._cfg.idle_timeout_s,
            "warning_grace_s": self._cfg.warning_grace_s,
            "reset_on_release": self._cfg.reset_on_release,
        }

        if self._current is None:
            return {
                "holder": None,
                "queue_length": len(self._queue),
                "queue": queue_list,
                "resetting": self._resetting,
                "paused": self._paused,
                "config": config,
            }
        return {
            "holder": self._current.holder,
            "remaining_s": self._remaining(),
            "queue_length": len(self._queue),
            "queue": queue_list,
            "resetting": self._resetting,
            "paused": self._paused,
            "config": config,
        }

    async def pause_queue(self) -> dict:
        """Pause queue progression — no queued holders will be granted."""
        async with self._lock:
            self._paused = True
            logger.info("Lease queue paused")
            return {"status": "paused"}

    async def resume_queue(self) -> dict:
        """Resume queue progression and grant next if nobody holds the lease."""
        async with self._lock:
            self._paused = False
            logger.info("Lease queue resumed")
            if self._current is None and not self._resetting:
                self._try_grant_next()
            return {"status": "resumed"}

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
        if self._on_lease_start:
            self._on_lease_start()
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
        if self._paused:
            return
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
        if self._cfg.reset_on_release and self._on_lease_end_async:
            self._resetting = True
            self._reset_task = asyncio.create_task(
                self._do_reset_and_grant(reason=reason)
            )
        else:
            self._try_grant_next()

    async def _do_reset_and_grant(self, reason: str = "released") -> None:
        """Rewind to home, clear trajectory, then grant next queued client."""
        try:
            self._on_event({"type": "resetting_to_home"})
            logger.info("Lease ended — resetting robot to home (reason: %s)", reason)

            # Stop any running code execution
            try:
                from routes.code_routes import get_executor
                executor = get_executor()
                if executor.is_running:
                    logger.info("Stopping running code execution before reset (reason: %s)", reason)
                    executor.stop(reason=reason)
            except Exception as e:
                logger.warning("Failed to stop code executor: %s", e)

            # Perform rewind + clear
            await self._on_lease_end_async()

            self._on_event({"type": "reset_complete"})
            logger.info("Reset to home complete")
        except asyncio.CancelledError:
            logger.info("Reset to home cancelled")
            raise
        except Exception as e:
            self._on_event({"type": "reset_failed", "error": str(e)})
            logger.error("Reset to home failed: %s", e)
        finally:
            async with self._lock:
                self._resetting = False
                self._try_grant_next()

    async def _check_loop(self) -> None:
        while True:
            await asyncio.sleep(self._cfg.check_interval_s)
            async with self._lock:
                if not self._current or self._resetting:
                    continue
                now = time.time()

                # Hard max duration
                if now - self._current.granted_at >= self._cfg.max_duration_s:
                    self._revoke("max_duration")
                    continue

                # Idle check — use most recent activity (command or movement)
                last_activity = max(self._current.last_cmd_at, self._last_moved_at())
                idle_s = now - last_activity

                if idle_s >= self._cfg.idle_timeout_s:
                    if not self._current.warned:
                        self._current.warned = True
                        self._on_event({
                            "type": "lease_warning",
                            "reason": "idle",
                            "seconds_remaining": self._cfg.warning_grace_s,
                        })
                    elif idle_s >= self._cfg.idle_timeout_s + self._cfg.warning_grace_s:
                        self._revoke("idle_timeout")
