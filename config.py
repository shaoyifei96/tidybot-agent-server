"""Configuration for the hardware server."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BaseBackendConfig:
    host: str = "localhost"
    port: int = 50000
    authkey: bytes = b"secret password"
    poll_hz: float = 10.0


@dataclass
class FrankaBackendConfig:
    host: str = "localhost"
    cmd_port: int = 5555
    state_port: int = 5556
    stream_port: int = 5557
    gripper_cmd_port: int = 5560
    gripper_state_port: int = 5561


@dataclass
class CameraConfig:
    enabled: bool = False
    devices: list[str] = field(default_factory=lambda: ["/dev/video0"])
    width: int = 640
    height: int = 480
    fps: int = 30


@dataclass
class SafetyConfig:
    # Arm workspace bounding box in base frame [min, max] for x, y, z (meters)
    arm_workspace_min: list[float] = field(default_factory=lambda: [-0.8, -0.8, 0.0])
    arm_workspace_max: list[float] = field(default_factory=lambda: [0.8, 0.8, 1.2])
    # Base workspace bounding box [min, max] for x, y (meters)
    base_workspace_min: list[float] = field(default_factory=lambda: [-5.0, -5.0])
    base_workspace_max: list[float] = field(default_factory=lambda: [5.0, 5.0])
    # Max velocities
    base_max_linear_vel: float = 0.5  # m/s
    base_max_angular_vel: float = 1.57  # rad/s
    arm_max_joint_vel: float = 2.0  # rad/s per joint
    # Gripper
    gripper_max_force: float = 70.0  # N


@dataclass
class LeaseConfig:
    idle_timeout_s: float = 30.0
    warning_grace_s: float = 10.0
    max_duration_s: float = 300.0
    check_interval_s: float = 1.0


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    dry_run: bool = False
    observer_state_hz: float = 10.0
    operator_state_hz: float = 100.0
    max_trajectory_length: int = 10000

    base: BaseBackendConfig = field(default_factory=BaseBackendConfig)
    franka: FrankaBackendConfig = field(default_factory=FrankaBackendConfig)
    cameras: CameraConfig = field(default_factory=CameraConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    lease: LeaseConfig = field(default_factory=LeaseConfig)
