"""FrankaServer ZMQ client wrapper (arm only)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from config import FrankaBackendConfig

logger = logging.getLogger(__name__)


class FrankaBackend:
    """Wraps FrankaClient for arm control."""

    def __init__(self, config: FrankaBackendConfig, dry_run: bool = False) -> None:
        self._cfg = config
        self._dry_run = dry_run
        self._client: Any = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        if self._dry_run:
            logger.info("FrankaBackend: dry-run mode, skipping connection")
            return

        # Import here so the server can start even without franka_server package
        # when in dry-run mode.
        import sys, os

        franka_pkg = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "franka_ZMQ",
            "franka_interact",
            "franka_server",
        )
        if franka_pkg not in sys.path:
            sys.path.insert(0, os.path.abspath(franka_pkg))

        from franka_server.client import FrankaClient

        self._client = FrankaClient(
            server_ip=self._cfg.host,
            cmd_port=self._cfg.cmd_port,
            state_port=self._cfg.state_port,
            stream_port=self._cfg.stream_port,
        )
        self._client.start()

        logger.info("FrankaBackend: connected to %s", self._cfg.host)

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.stop()
            self._client = None
        logger.info("FrankaBackend: disconnected")

    @property
    def is_connected(self) -> bool:
        """Return True if connected to franka server."""
        return self._dry_run or self._client is not None

    # -- state ---------------------------------------------------------------

    def get_state(self) -> dict:
        """Return arm state as a plain dict."""
        if self._dry_run:
            return {
                "q": [0.0] * 7,
                "dq": [0.0] * 7,
                "ee_pose": [0.0] * 16,
                "ee_wrench": [0.0] * 6,
                "control_mode": 0,
            }
        state = self._client.latest_state
        if state is None:
            return {}
        return {
            "q": list(state.q),
            "dq": list(state.dq),
            "ee_pose": list(state.O_T_EE),
            "ee_wrench": list(state.O_F_ext_hat_K),
            "control_mode": int(state.control_mode),
        }

    # -- arm commands --------------------------------------------------------

    def send_joint_position(self, q: list[float], blocking: bool = True) -> bool:
        if self._dry_run:
            return True
        return self._client.send_joint_position(np.array(q), blocking=blocking)

    def send_cartesian_pose(self, pose: list[float]) -> bool:
        if self._dry_run:
            return True
        return self._client.send_cartesian_pose(np.array(pose), blocking=True)

    def send_joint_velocity(self, dq: list[float]) -> bool:
        if self._dry_run:
            return True
        return self._client.send_joint_velocity(np.array(dq), blocking=True)

    def send_cartesian_velocity(self, velocity: list[float]) -> bool:
        if self._dry_run:
            return True
        return self._client.send_cartesian_velocity(np.array(velocity), blocking=True)

    def set_control_mode(self, mode: int) -> bool:
        if self._dry_run:
            return True
        return self._client.set_control_mode(mode)

    def emergency_stop(self) -> bool:
        if self._dry_run:
            return True
        return self._client.emergency_stop()
