"""Simple arm controller using the agent server HTTP API.

Supports three control modes:
1. Absolute joint mode - move to specific joint angles
2. Delta pose mode - move relative to current end-effector pose
3. Global pose mode - move to absolute pose in robot base frame

Example usage:
    from controllers import ArmController

    arm = ArmController()
    arm.acquire_lease("my-controller")

    # Move to joint position
    arm.move_joints([0.0, -0.5, 0.0, -2.0, 0.0, 1.5, 0.7])

    # Move 10cm forward in x (delta)
    arm.move_delta(dx=0.1)

    # Move to absolute position
    arm.move_to_pose(x=0.5, y=0.0, z=0.4)

    arm.release_lease()
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import requests


@dataclass
class Pose:
    """End-effector pose with position and orientation (quaternion)."""
    x: float
    y: float
    z: float
    qw: float = 1.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0

    @classmethod
    def from_matrix(cls, matrix: np.ndarray) -> "Pose":
        """Create Pose from 4x4 transformation matrix."""
        x, y, z = matrix[0, 3], matrix[1, 3], matrix[2, 3]
        qw, qx, qy, qz = rotation_matrix_to_quaternion(matrix[:3, :3])
        return cls(x=x, y=y, z=z, qw=qw, qx=qx, qy=qy, qz=qz)

    def to_matrix(self) -> np.ndarray:
        """Convert to 4x4 transformation matrix."""
        mat = np.eye(4)
        mat[:3, :3] = quaternion_to_rotation_matrix(self.qw, self.qx, self.qy, self.qz)
        mat[0, 3] = self.x
        mat[1, 3] = self.y
        mat[2, 3] = self.z
        return mat

    def __repr__(self) -> str:
        return f"Pose(x={self.x:.3f}, y={self.y:.3f}, z={self.z:.3f})"


def rotation_matrix_to_quaternion(R: np.ndarray) -> tuple[float, float, float, float]:
    """Convert 3x3 rotation matrix to quaternion (w, x, y, z)."""
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return (w, x, y, z)


def quaternion_to_rotation_matrix(w: float, x: float, y: float, z: float) -> np.ndarray:
    """Convert quaternion to 3x3 rotation matrix."""
    # Normalize quaternion
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n

    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def euler_to_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Convert Euler angles (RPY) to 3x3 rotation matrix. Angles in radians."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)

    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])


class ArmController:
    """Simple arm controller using agent server HTTP API.

    Coordinate frames:
    - Joint positions are in radians
    - Cartesian poses are in the robot base frame (O frame)
    - ee_pose from state is O_T_EE (base to end-effector transform)
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

    def acquire_lease(self, holder: str = "arm-controller") -> str:
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

    def get_joint_positions(self) -> list[float]:
        """Get current joint positions (7 values in radians)."""
        state = self.get_state()
        return state.get("arm", {}).get("q", [0.0] * 7)

    def get_ee_pose(self) -> Pose:
        """Get current end-effector pose in base frame."""
        state = self.get_state()
        ee_pose_flat = state.get("arm", {}).get("ee_pose", [])
        if len(ee_pose_flat) != 16:
            # Return identity pose if no data available
            return Pose(x=0.0, y=0.0, z=0.0)
        # Convert column-major flat array to 4x4 matrix
        matrix = np.array(ee_pose_flat).reshape(4, 4, order="F")
        return Pose.from_matrix(matrix)

    def get_ee_matrix(self) -> np.ndarray:
        """Get current end-effector pose as 4x4 matrix."""
        state = self.get_state()
        ee_pose_flat = state.get("arm", {}).get("ee_pose", [])
        if len(ee_pose_flat) != 16:
            # Return identity matrix if no data available
            return np.eye(4)
        return np.array(ee_pose_flat).reshape(4, 4, order="F")

    # -- Control commands -----------------------------------------------------

    def move_joints(self, q: list[float], blocking: bool = True) -> dict:
        """Move to absolute joint positions.

        Args:
            q: 7 joint angles in radians
            blocking: If True (default), wait for motion to complete

        Returns:
            Response dict with status
        """
        if len(q) != 7:
            raise ValueError(f"Expected 7 joint values, got {len(q)}")

        resp = requests.post(
            f"{self.server_url}/cmd/arm/move",
            headers=self._headers(),
            json={"mode": "joint_position", "values": list(q)},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def move_to_matrix(self, matrix: np.ndarray) -> dict:
        """Move to absolute pose specified as 4x4 transformation matrix.

        Args:
            matrix: 4x4 homogeneous transformation matrix (base frame)

        Returns:
            Response dict with status
        """
        # Flatten to column-major order (Fortran order) as expected by Franka
        pose_flat = matrix.flatten(order="F").tolist()

        resp = requests.post(
            f"{self.server_url}/cmd/arm/move",
            headers=self._headers(),
            json={"mode": "cartesian_pose", "values": pose_flat},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def move_to_pose(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        keep_orientation: bool = True,
    ) -> dict:
        """Move to absolute pose in base frame.

        Args:
            x, y, z: Target position in meters (None = keep current)
            roll, pitch, yaw: Target orientation in radians (ignored if keep_orientation=True)
            keep_orientation: If True, maintain current orientation

        Returns:
            Response dict with status
        """
        current = self.get_ee_matrix()
        target = current.copy()

        # Update position
        if x is not None:
            target[0, 3] = x
        if y is not None:
            target[1, 3] = y
        if z is not None:
            target[2, 3] = z

        # Update orientation if requested
        if not keep_orientation:
            target[:3, :3] = euler_to_rotation_matrix(roll, pitch, yaw)

        return self.move_to_matrix(target)

    def move_delta(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        droll: float = 0.0,
        dpitch: float = 0.0,
        dyaw: float = 0.0,
        frame: str = "base",
    ) -> dict:
        """Move relative to current pose.

        Args:
            dx, dy, dz: Position delta in meters
            droll, dpitch, dyaw: Orientation delta in radians
            frame: "base" for world frame deltas, "ee" for end-effector frame deltas

        Returns:
            Response dict with status
        """
        current = self.get_ee_matrix()

        # Create delta transform
        delta = np.eye(4)
        delta[:3, :3] = euler_to_rotation_matrix(droll, dpitch, dyaw)
        delta[0, 3] = dx
        delta[1, 3] = dy
        delta[2, 3] = dz

        if frame == "base":
            # Apply delta in base frame: T_new = delta @ T_current (for position)
            # For pure translation in base frame:
            target = current.copy()
            target[0, 3] += dx
            target[1, 3] += dy
            target[2, 3] += dz
            # For rotation, apply in base frame
            if droll != 0 or dpitch != 0 or dyaw != 0:
                rot_delta = euler_to_rotation_matrix(droll, dpitch, dyaw)
                target[:3, :3] = rot_delta @ current[:3, :3]
        else:
            # Apply delta in end-effector frame: T_new = T_current @ delta
            target = current @ delta

        return self.move_to_matrix(target)

    def stop(self) -> dict:
        """Emergency stop the arm."""
        resp = requests.post(
            f"{self.server_url}/cmd/arm/stop",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    # -- Convenience methods --------------------------------------------------

    def home(self) -> dict:
        """Move to a safe home position."""
        home_joints = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785]
        return self.move_joints(home_joints)

    def print_state(self) -> None:
        """Print current arm state."""
        joints = self.get_joint_positions()
        pose = self.get_ee_pose()
        if joints:
            print(f"Joints: [{', '.join(f'{q:.3f}' for q in joints)}]")
        else:
            print("Joints: [no data - franka backend not connected]")
        print(f"EE pose: x={pose.x:.3f}, y={pose.y:.3f}, z={pose.z:.3f}")

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> "ArmController":
        return self

    def __exit__(self, *args) -> None:
        self.release_lease()
