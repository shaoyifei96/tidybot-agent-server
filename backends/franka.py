"""FrankaServer ZMQ client wrapper (arm + gripper)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from config import FrankaBackendConfig

logger = logging.getLogger(__name__)


class FrankaBackend:
    """Wraps FrankaClient and optional standalone GripperClient."""

    def __init__(self, config: FrankaBackendConfig, dry_run: bool = False) -> None:
        self._cfg = config
        self._dry_run = dry_run
        self._client: Any = None
        self._gripper: Any = None

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
        from franka_server.gripper_client import GripperClient

        self._client = FrankaClient(
            server_ip=self._cfg.host,
            cmd_port=self._cfg.cmd_port,
            state_port=self._cfg.state_port,
            stream_port=self._cfg.stream_port,
        )
        self._client.start()

        self._gripper = GripperClient(
            server_ip=self._cfg.host,
            cmd_port=self._cfg.gripper_cmd_port,
            state_port=self._cfg.gripper_state_port,
        )
        self._gripper.connect()

        logger.info("FrankaBackend: connected to %s", self._cfg.host)

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.stop()
            self._client = None
        if self._gripper is not None:
            self._gripper.disconnect()
            self._gripper = None
        logger.info("FrankaBackend: disconnected")

    # -- state ---------------------------------------------------------------

    def get_state(self) -> dict:
        """Return arm + gripper state as a plain dict."""
        if self._dry_run:
            return {
                "q": [0.0] * 7,
                "dq": [0.0] * 7,
                "ee_pose": [0.0] * 16,
                "ee_wrench": [0.0] * 6,
                "gripper_width": 0.04,
                "gripper_is_grasped": False,
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
            "gripper_width": state.gripper_width,
            "gripper_is_grasped": state.gripper_is_grasped,
            "control_mode": int(state.control_mode),
        }

    # -- arm commands --------------------------------------------------------

    def send_joint_position(self, q: list[float]) -> bool:
        if self._dry_run:
            return True
        return self._client.send_joint_position(np.array(q), blocking=True)

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

    # -- gripper commands ----------------------------------------------------

    def gripper_move(self, width: float, speed: float = 0.1) -> bool:
        if self._dry_run:
            return True
        return self._gripper.move(width, speed)

    def gripper_grasp(
        self,
        width: float,
        speed: float = 0.1,
        force: float = 20.0,
        epsilon_inner: float = 0.005,
        epsilon_outer: float = 0.005,
    ) -> bool:
        if self._dry_run:
            return True
        return self._gripper.grasp(width, speed, force, epsilon_inner, epsilon_outer)

    def gripper_open(self, speed: float = 0.1) -> bool:
        if self._dry_run:
            return True
        return self._gripper.open(speed)

    def gripper_close(self, speed: float = 0.1) -> bool:
        if self._dry_run:
            return True
        return self._gripper.close(speed)

    def gripper_stop(self) -> bool:
        if self._dry_run:
            return True
        return self._gripper.stop()

    def gripper_homing(self) -> bool:
        if self._dry_run:
            return True
        return self._gripper.homing()
