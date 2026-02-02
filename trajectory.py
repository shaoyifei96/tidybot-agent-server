"""Trajectory recorder — stores waypoints after each position command."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Waypoint:
    t: float
    base_pose: list[float]
    arm_q: list[float]
    gripper_width: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "base_pose": self.base_pose,
            "arm_q": self.arm_q,
            "gripper_width": self.gripper_width,
        }


class TrajectoryRecorder:
    """Records waypoints after successful position commands."""

    def __init__(self, max_length: int = 10000) -> None:
        self._max_length = max_length
        self._waypoints: list[Waypoint] = []

    def record(self, state: dict[str, Any]) -> None:
        """Snapshot current state as a waypoint."""
        wp = Waypoint(
            t=time.time(),
            base_pose=list(state.get("base", {}).get("pose", [0, 0, 0])),
            arm_q=list(state.get("arm", {}).get("q", [])),
            gripper_width=state.get("gripper", {}).get("width", 0.0),
        )
        self._waypoints.append(wp)
        if len(self._waypoints) > self._max_length:
            self._waypoints = self._waypoints[-self._max_length :]

    def get_history(self) -> list[dict[str, Any]]:
        return [wp.to_dict() for wp in self._waypoints]

    def truncate(self, keep_n: int) -> None:
        """Keep only the first keep_n waypoints."""
        self._waypoints = self._waypoints[:keep_n]

    def clear(self) -> None:
        self._waypoints.clear()

    def __len__(self) -> int:
        return len(self._waypoints)
