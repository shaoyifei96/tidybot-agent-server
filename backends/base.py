"""BaseServer RPC client wrapper."""

from __future__ import annotations

import logging
import multiprocessing.managers
from typing import Any

import numpy as np

from config import BaseBackendConfig

logger = logging.getLogger(__name__)


class _BaseManager(multiprocessing.managers.BaseManager):
    pass


_BaseManager.register("Base")


class BaseBackend:
    """Thin wrapper around BaseServer's multiprocessing RPC interface."""

    def __init__(self, config: BaseBackendConfig, dry_run: bool = False) -> None:
        self._cfg = config
        self._dry_run = dry_run
        self._manager: _BaseManager | None = None
        self._base: Any = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        if self._dry_run:
            logger.info("BaseBackend: dry-run mode, skipping connection")
            return
        self._manager = _BaseManager(
            address=(self._cfg.host, self._cfg.port),
            authkey=self._cfg.authkey,
        )
        self._manager.connect()
        self._base = self._manager.Base()  # type: ignore[attr-defined]
        logger.info("BaseBackend: connected to %s:%d", self._cfg.host, self._cfg.port)

    async def disconnect(self) -> None:
        self._base = None
        self._manager = None
        logger.info("BaseBackend: disconnected")

    # -- queries -------------------------------------------------------------

    def get_state(self) -> dict:
        """Return ``{'base_pose': [x, y, theta]}``."""
        if self._dry_run:
            return {"base_pose": [0.0, 0.0, 0.0]}
        raw = self._base.get_state()
        pose = raw.get("base_pose")
        if isinstance(pose, np.ndarray):
            pose = pose.tolist()
        return {"base_pose": pose}

    # -- commands ------------------------------------------------------------

    def execute_action(self, x: float, y: float, theta: float) -> None:
        if self._dry_run:
            return
        self._base.execute_action({"base_pose": np.array([x, y, theta])})

    def set_target_velocity(
        self, vx: float, vy: float, wz: float, frame: str = "global"
    ) -> None:
        if self._dry_run:
            return
        self._base.set_target_velocity([vx, vy, wz], frame=frame)

    def stop(self) -> None:
        if self._dry_run:
            return
        self._base.stop()

    def reset(self) -> None:
        if self._dry_run:
            return
        self._base.reset()
