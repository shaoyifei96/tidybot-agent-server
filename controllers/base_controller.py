"""Simple base controller using the agent server HTTP API.

Supports two control modes:
1. Delta pose mode - move relative to current base pose
2. Global pose mode - move to absolute pose (x, y, theta)

Example usage:
    from controllers import BaseController

    base = BaseController()
    base.acquire_lease("my-controller")

    # Move 0.5m forward
    base.move_delta(dx=0.5)

    # Rotate 90 degrees
    base.move_delta(dtheta=1.57)

    # Move to absolute position
    base.move_to_pose(x=1.0, y=0.5, theta=0.0)

    base.release_lease()
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class BasePose:
    """Base pose with position (x, y) and orientation (theta)."""
    x: float
    y: float
    theta: float

    def __repr__(self) -> str:
        return f"BasePose(x={self.x:.3f}, y={self.y:.3f}, theta={math.degrees(self.theta):.1f}deg)"


class BaseController:
    """Simple base controller using agent server HTTP API.

    Coordinate frame:
    - x: forward (positive = forward)
    - y: left (positive = left)
    - theta: rotation around z (positive = counter-clockwise)
    - All units are meters and radians
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8080",
        timeout: float = 30.0,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._lease_id: Optional[str] = None
        self._holder: Optional[str] = None

    # -- Lease management -----------------------------------------------------

    def acquire_lease(self, holder: str = "base-controller") -> str:
        """Acquire control lease. Returns lease_id."""
        resp = requests.post(
            f"{self.server_url}/lease/acquire",
            json={"holder": holder},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        self._lease_id = data["lease_id"]
        self._holder = holder
        return self._lease_id

    def release_lease(self) -> None:
        """Release control lease."""
        if self._lease_id:
            requests.post(
                f"{self.server_url}/lease/release",
                json={"lease_id": self._lease_id},
                timeout=self.timeout,
            )
            self._lease_id = None
            self._holder = None

    def _headers(self) -> dict:
        """Get request headers with lease ID."""
        headers = {"Content-Type": "application/json"}
        if self._lease_id:
            headers["X-Lease-Id"] = self._lease_id
        return headers

    # -- State ----------------------------------------------------------------

    def get_state(self) -> dict:
        """Get current robot state."""
        resp = requests.get(f"{self.server_url}/state", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_pose(self) -> BasePose:
        """Get current base pose (x, y, theta)."""
        state = self.get_state()
        pose = state.get("base", {}).get("pose", [0.0, 0.0, 0.0])
        return BasePose(x=pose[0], y=pose[1], theta=pose[2])

    # -- Control commands -----------------------------------------------------

    def move_to_pose(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        theta: Optional[float] = None,
    ) -> dict:
        """Move to absolute pose (global frame).

        Args:
            x: Target x position in meters (None = keep current)
            y: Target y position in meters (None = keep current)
            theta: Target orientation in radians (None = keep current)

        Returns:
            Response dict with status
        """
        current = self.get_pose()

        target_x = x if x is not None else current.x
        target_y = y if y is not None else current.y
        target_theta = theta if theta is not None else current.theta

        resp = requests.post(
            f"{self.server_url}/cmd/base/move",
            headers=self._headers(),
            json={"x": target_x, "y": target_y, "theta": target_theta},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def move_delta(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dtheta: float = 0.0,
        frame: str = "global",
    ) -> dict:
        """Move relative to current pose.

        Args:
            dx: Position delta in x (meters)
            dy: Position delta in y (meters)
            dtheta: Orientation delta in radians
            frame: "global" for world frame deltas, "local" for robot frame deltas

        Returns:
            Response dict with status
        """
        current = self.get_pose()

        if frame == "local":
            # Transform local delta to global frame
            cos_t = math.cos(current.theta)
            sin_t = math.sin(current.theta)
            global_dx = cos_t * dx - sin_t * dy
            global_dy = sin_t * dx + cos_t * dy
        else:
            global_dx = dx
            global_dy = dy

        target_x = current.x + global_dx
        target_y = current.y + global_dy
        target_theta = current.theta + dtheta

        # Normalize theta to [-pi, pi]
        target_theta = math.atan2(math.sin(target_theta), math.cos(target_theta))

        resp = requests.post(
            f"{self.server_url}/cmd/base/move",
            headers=self._headers(),
            json={"x": target_x, "y": target_y, "theta": target_theta},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def move_velocity(
        self,
        vx: float = 0.0,
        vy: float = 0.0,
        wz: float = 0.0,
        frame: str = "global",
    ) -> dict:
        """Send velocity command.

        Args:
            vx: Linear velocity in x (m/s)
            vy: Linear velocity in y (m/s)
            wz: Angular velocity around z (rad/s)
            frame: "global" or "local"

        Returns:
            Response dict with status
        """
        resp = requests.post(
            f"{self.server_url}/cmd/base/move",
            headers=self._headers(),
            json={"vx": vx, "vy": vy, "wz": wz, "frame": frame},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def stop(self) -> dict:
        """Stop base movement."""
        resp = requests.post(
            f"{self.server_url}/cmd/base/stop",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    # -- Convenience methods --------------------------------------------------

    def forward(self, distance: float) -> dict:
        """Move forward by specified distance (meters)."""
        return self.move_delta(dx=distance, frame="local")

    def backward(self, distance: float) -> dict:
        """Move backward by specified distance (meters)."""
        return self.move_delta(dx=-distance, frame="local")

    def left(self, distance: float) -> dict:
        """Strafe left by specified distance (meters)."""
        return self.move_delta(dy=distance, frame="local")

    def right(self, distance: float) -> dict:
        """Strafe right by specified distance (meters)."""
        return self.move_delta(dy=-distance, frame="local")

    def rotate(self, angle: float) -> dict:
        """Rotate by specified angle (radians, positive = CCW)."""
        return self.move_delta(dtheta=angle)

    def rotate_degrees(self, degrees: float) -> dict:
        """Rotate by specified angle (degrees, positive = CCW)."""
        return self.move_delta(dtheta=math.radians(degrees))

    def print_state(self) -> None:
        """Print current base state."""
        pose = self.get_pose()
        print(f"Base pose: x={pose.x:.3f}m, y={pose.y:.3f}m, theta={math.degrees(pose.theta):.1f}deg")

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> "BaseController":
        return self

    def __exit__(self, *args) -> None:
        self.release_lease()
