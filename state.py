"""Unified state aggregator — merges base + arm + gripper state."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backends.base import BaseBackend
from backends.franka import FrankaBackend
from config import ServerConfig

logger = logging.getLogger(__name__)


class StateAggregator:
    """Polls backends and maintains a unified snapshot of robot state."""

    def __init__(
        self,
        config: ServerConfig,
        base: BaseBackend,
        franka: FrankaBackend,
    ) -> None:
        self._cfg = config
        self._base = base
        self._franka = franka
        self._state: dict[str, Any] = {}
        self._task: asyncio.Task | None = None

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def motors_moving(self) -> bool:
        """Return True if any motor has significant velocity."""
        arm = self._state.get("arm", {})
        dq = arm.get("dq", [])
        if any(abs(v) > 0.01 for v in dq):
            return True
        base = self._state.get("base", {})
        pose = base.get("pose", [0, 0, 0])
        # Base doesn't expose velocity directly; we'd need to diff poses.
        # For now, rely on arm velocity only.
        return False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        interval = 1.0 / self._cfg.base.poll_hz
        while True:
            try:
                loop = asyncio.get_event_loop()
                base_state = await loop.run_in_executor(None, self._base.get_state)
                franka_state = await loop.run_in_executor(None, self._franka.get_state)

                self._state = {
                    "timestamp": time.time(),
                    "base": {"pose": base_state.get("base_pose", [0, 0, 0])},
                    "arm": {
                        "q": franka_state.get("q", []),
                        "dq": franka_state.get("dq", []),
                        "ee_pose": franka_state.get("ee_pose", []),
                        "ee_wrench": franka_state.get("ee_wrench", []),
                        "mode": franka_state.get("control_mode", 0),
                    },
                    "gripper": {
                        "width": franka_state.get("gripper_width", 0.0),
                        "is_grasped": franka_state.get("gripper_is_grasped", False),
                    },
                    "motors_moving": self.motors_moving(),
                }
            except Exception:
                logger.exception("State poll error")
            await asyncio.sleep(interval)
