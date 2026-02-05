"""Arm control API for submitted code."""

from __future__ import annotations

import time
from typing import Optional
import numpy as np

from backends.franka import FrankaBackend


class ArmError(Exception):
    """Raised when arm command fails."""
    pass


class ArmAPI:
    """High-level arm control API for Franka Panda arm.

    All methods are synchronous (blocking) and wait until motion completes.
    Raises ArmError on failure. Robot holds position on error (auto-hold).

    Example:
        from robot_sdk import arm

        # Move to joint position
        arm.move_joints([0, -0.785, 0, -2.356, 0, 1.571, 0.785])

        # Move to cartesian pose
        arm.move_to_pose(x=0.5, y=0.0, z=0.3)

        # Delta movement
        arm.move_delta(dz=0.1, frame="ee")

    Note:
        Commands are sent at 50 Hz internally until target is reached.
        Control mode is set automatically (JOINT_POSITION or CARTESIAN_POSE).
    """

    # Control mode constants
    MODE_IDLE = 0
    MODE_JOINT_POSITION = 1
    MODE_JOINT_VELOCITY = 2
    MODE_TORQUE = 3
    MODE_CARTESIAN_POSE = 4
    MODE_CARTESIAN_VELOCITY = 5

    def __init__(self, backend: FrankaBackend) -> None:
        self._backend = backend
        self._timeout = 30.0  # Default timeout for blocking operations
        self._command_rate = 50.0  # Hz for streaming commands
        self._default_duration = 3.0  # Default motion duration in seconds

    @staticmethod
    def _cubic_ease_in_out(t: float) -> float:
        """Cubic ease-in-out interpolation for smooth motion."""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2

    def move_joints(
        self,
        q: list[float],
        timeout: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> None:
        """Move arm to joint positions with smooth interpolation (blocking).

        Interpolates from current position to target using cubic ease-in-out
        for smooth, jerk-free motion. Sends commands at 50 Hz.

        Args:
            q: List of 7 joint angles in radians.
               Home position: [0, -0.785, 0, -2.356, 0, 1.571, 0.785]
            timeout: Max time to wait in seconds (default: 30s)
            duration: Motion duration in seconds (default: 3s, auto-adjusts for large moves)

        Raises:
            ArmError: If timeout or command fails

        Example:
            arm.move_joints([0, -0.785, 0, -2.356, 0, 1.571, 0.785])
            arm.move_joints(target, duration=5.0)  # Slower 5-second motion
        """
        if len(q) != 7:
            raise ArmError(f"Expected 7 joint angles, got {len(q)}")

        timeout = timeout or self._timeout

        # Set control mode first and wait for it to take effect
        self._backend.set_control_mode(self.MODE_JOINT_POSITION)
        time.sleep(0.1)  # Wait for mode switch

        # Get fresh current position (read multiple times to ensure fresh)
        for _ in range(3):
            state = self._backend.get_state()
            time.sleep(0.02)
        start_q = state.get("q", [0.0] * 7)

        # Calculate max joint displacement
        max_delta = max(abs(q[i] - start_q[i]) for i in range(7))

        # Auto-adjust duration: slower to prevent velocity violations
        # At least 2 seconds per 0.5 rad (30 deg), minimum 2s
        if duration is None:
            duration = max(2.0, min(15.0, max_delta / 0.5 * 4.0))

        # Send current position first to establish command stream (avoids jump)
        for _ in range(5):
            self._backend.send_joint_position(start_q, blocking=False)
            time.sleep(0.02)

        # Interpolate smoothly from start to target
        command_interval = 1.0 / self._command_rate
        motion_start_time = time.time()
        start_time = motion_start_time

        while time.time() - start_time < timeout:
            elapsed = time.time() - motion_start_time
            t = min(1.0, elapsed / duration)  # Normalized time [0, 1]

            # Cubic ease-in-out interpolation
            alpha = self._cubic_ease_in_out(t)

            # Interpolate joint positions
            interp_q = [start_q[i] + alpha * (q[i] - start_q[i]) for i in range(7)]

            # Send interpolated command
            self._backend.send_joint_position(interp_q, blocking=False)

            # Check if motion complete
            if t >= 1.0:
                # Verify we've reached target
                state = self._backend.get_state()
                current_q = state.get("q", [0.0] * 7)
                dq = state.get("dq", [0.0] * 7)

                errors = [abs(current_q[i] - q[i]) for i in range(7)]
                max_error = max(errors)
                max_vel = max(abs(v) for v in dq)

                # Done if close to target and not moving much
                if max_error < 0.02 and max_vel < 0.05:
                    return

            time.sleep(command_interval)

        raise ArmError(f"Timeout waiting for arm to reach target position")

    def move_to_pose(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        roll: Optional[float] = None,
        pitch: Optional[float] = None,
        yaw: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Move end-effector to cartesian pose (blocking).

        Args:
            x, y, z: Position in meters (optional, keeps current if None)
            roll, pitch, yaw: Orientation in radians (optional, keeps current if None)
            timeout: Optional timeout in seconds (default: 30s)

        Raises:
            ArmError: If command fails or timeout
        """
        # Get current pose
        state = self._backend.get_state()
        current_pose = state.get("ee_pose", [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1])

        # Extract current position and rotation
        current_x, current_y, current_z = current_pose[12], current_pose[13], current_pose[14]

        # Use provided values or keep current
        target_x = x if x is not None else current_x
        target_y = y if y is not None else current_y
        target_z = z if z is not None else current_z

        # For orientation, if any RPY is specified, use them; otherwise keep current rotation
        if roll is not None or pitch is not None or yaw is not None:
            # Use provided values or zero for unspecified
            r = roll if roll is not None else 0.0
            p = pitch if pitch is not None else 0.0
            y_angle = yaw if yaw is not None else 0.0

            # Convert RPY to rotation matrix
            rot_matrix = self._rpy_to_matrix(r, p, y_angle)
        else:
            # Keep current rotation (top-left 3x3 of pose matrix)
            rot_matrix = np.array([
                [current_pose[0], current_pose[4], current_pose[8]],
                [current_pose[1], current_pose[5], current_pose[9]],
                [current_pose[2], current_pose[6], current_pose[10]],
            ])

        # Build 4x4 transformation matrix (column-major)
        target_pose = [
            rot_matrix[0, 0], rot_matrix[1, 0], rot_matrix[2, 0], 0.0,
            rot_matrix[0, 1], rot_matrix[1, 1], rot_matrix[2, 1], 0.0,
            rot_matrix[0, 2], rot_matrix[1, 2], rot_matrix[2, 2], 0.0,
            target_x, target_y, target_z, 1.0,
        ]

        timeout = timeout or self._timeout

        # Set control mode to CARTESIAN_POSE
        self._backend.set_control_mode(self.MODE_CARTESIAN_POSE)
        time.sleep(0.05)

        # Send commands continuously until target reached
        command_interval = 1.0 / self._command_rate
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Send command
            self._backend.send_cartesian_pose(target_pose)

            # Check if we've reached target
            state = self._backend.get_state()
            current_pose = state.get("ee_pose", [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1])
            dq = state.get("dq", [0.0] * 7)

            # Check position error
            pos_error = (
                (current_pose[12] - target_x)**2 +
                (current_pose[13] - target_y)**2 +
                (current_pose[14] - target_z)**2
            ) ** 0.5

            max_vel = max(abs(v) for v in dq)

            # Done if close to target and not moving much
            if pos_error < 0.005 and max_vel < 0.05:  # 5mm error, low velocity
                return

            time.sleep(command_interval)

        raise ArmError("Timeout waiting for arm to reach target pose")

    def move_delta(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        frame: str = "base",
        timeout: Optional[float] = None,
    ) -> None:
        """Move end-effector by delta in specified frame (blocking).

        Args:
            dx, dy, dz: Delta position in meters
            frame: "base" (default) or "ee" (end-effector frame)
            timeout: Optional timeout in seconds (default: 30s)

        Raises:
            ArmError: If command fails or timeout
        """
        # Get current pose
        state = self._backend.get_state()
        current_pose = state.get("ee_pose", [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1])

        current_x = current_pose[12]
        current_y = current_pose[13]
        current_z = current_pose[14]

        if frame == "base":
            # Delta in base frame (simple addition)
            target_x = current_x + dx
            target_y = current_y + dy
            target_z = current_z + dz
        elif frame == "ee":
            # Delta in end-effector frame (transform by current rotation)
            rot_matrix = np.array([
                [current_pose[0], current_pose[4], current_pose[8]],
                [current_pose[1], current_pose[5], current_pose[9]],
                [current_pose[2], current_pose[6], current_pose[10]],
            ])
            delta_ee = np.array([dx, dy, dz])
            delta_base = rot_matrix @ delta_ee

            target_x = current_x + delta_base[0]
            target_y = current_y + delta_base[1]
            target_z = current_z + delta_base[2]
        else:
            raise ArmError(f"Invalid frame: {frame}. Must be 'base' or 'ee'")

        # Move to target position (keeping current orientation)
        self.move_to_pose(x=target_x, y=target_y, z=target_z, timeout=timeout)

    def get_state(self) -> dict:
        """Get current arm state.

        Returns:
            Dictionary with keys: q, dq, ee_pose, ee_wrench, control_mode
        """
        return self._backend.get_state()

    def stop(self) -> None:
        """Emergency stop the arm.

        Raises:
            ArmError: If stop command fails
        """
        success = self._backend.emergency_stop()
        if not success:
            raise ArmError("Failed to send emergency stop command")

    # Home position for Franka Panda
    HOME_POSITION = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785]

    def go_home(self, timeout: Optional[float] = None, duration: Optional[float] = None) -> None:
        """Move arm to home position with smooth interpolation (blocking).

        Home position: [0, -0.785, 0, -2.356, 0, 1.571, 0.785] radians

        Args:
            timeout: Max time to wait in seconds (default: 30s)
            duration: Motion duration in seconds (default: auto-calculated)

        Raises:
            ArmError: If timeout or command fails

        Example:
            arm.go_home()
            arm.go_home(duration=5.0)  # Slower motion
        """
        self.move_joints(self.HOME_POSITION, timeout=timeout, duration=duration)

    @staticmethod
    def _rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
        """Convert roll-pitch-yaw to rotation matrix."""
        cr, sr = np.cos(roll), np.sin(roll)
        cp, sp = np.cos(pitch), np.sin(pitch)
        cy, sy = np.cos(yaw), np.sin(yaw)

        return np.array([
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ])
