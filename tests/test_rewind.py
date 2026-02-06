#!/usr/bin/env python3
"""Test script for rewind functionality.

This script tests the rewind logic by:
1. Creating mock backends
2. Manually adding waypoints to the trajectory
3. Testing rewind by percentage and reset-to-home

Usage:
    python3 test_rewind.py
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

# Add parent directory to path for imports
import sys
sys.path.insert(0, '.')

from trajectory import TrajectoryRecorder, Waypoint
from safety import SafetyEnvelope
from config import SafetyConfig
from rewind import RewindManager, RewindConfig, SafetyMonitor


# -- Mock Backends -----------------------------------------------------------

class MockBaseBackend:
    """Mock base backend for testing."""

    def __init__(self):
        self.current_pose = [0.0, 0.0, 0.0]  # x, y, theta
        self.move_history = []

    def get_state(self) -> dict:
        return {"base_pose": self.current_pose}

    def execute_action(self, x: float, y: float, theta: float) -> None:
        self.current_pose = [x, y, theta]
        self.move_history.append([x, y, theta])
        print(f"  [MockBase] Moved to ({x:.3f}, {y:.3f}, {theta:.3f})")


# -- Test Functions ----------------------------------------------------------

def create_test_trajectory(trajectory: TrajectoryRecorder, n_waypoints: int = 10):
    """Create fake waypoints simulating robot movement.

    Note: In production, waypoints are recorded automatically by the
    time-driven TrajectoryRecorder. This function manually creates
    waypoints for testing purposes.
    """
    print(f"\n=== Creating {n_waypoints} test waypoints ===\n")

    for i in range(n_waypoints):
        t = time.time() + i * 0.1  # 100ms between waypoints (matches default interval)

        # Simulate base moving in a line
        base_pose = [i * 0.5, i * 0.3, i * 0.1]

        # Simulate arm moving slightly
        arm_q = [0.1 * i, -0.785 + 0.05 * i, 0.0, -2.356, 0.0, 1.571, 0.785]

        # Simulate gripper opening/closing
        gripper_width = 0.08 - (i * 0.005)  # Slowly closing

        wp = Waypoint(t=t, base_pose=base_pose, arm_q=arm_q, gripper_width=gripper_width)
        trajectory._waypoints.append(wp)

        print(f"  Waypoint {i}: base=({base_pose[0]:.2f}, {base_pose[1]:.2f}), "
              f"gripper={gripper_width:.3f}m")

    print(f"\nTrajectory length: {len(trajectory)} waypoints")


async def test_rewind_percentage(rewind_mgr: RewindManager, percentage: float):
    """Test rewinding by percentage."""
    print(f"\n=== Testing rewind {percentage}% ===\n")

    initial_len = rewind_mgr.trajectory_length
    print(f"Initial trajectory length: {initial_len}")

    result = await rewind_mgr.rewind_percentage(percentage)

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Steps rewound: {result.steps_rewound}")
    print(f"  Start waypoint: {result.start_waypoint_idx}")
    print(f"  End waypoint: {result.end_waypoint_idx}")
    if result.error:
        print(f"  Error: {result.error}")

    print(f"\nTrajectory length after rewind: {rewind_mgr.trajectory_length}")

    return result


async def test_reset_to_home(safety_monitor: SafetyMonitor):
    """Test reset to home (100% rewind)."""
    print(f"\n=== Testing Reset to Home (100% rewind) ===\n")

    initial_len = safety_monitor._rewind_mgr.trajectory_length
    print(f"Initial trajectory length: {initial_len}")

    result = await safety_monitor.reset_to_home()

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Steps rewound: {result.steps_rewound}")
    if result.error:
        print(f"  Error: {result.error}")

    print(f"\nTrajectory length after reset: {safety_monitor._rewind_mgr.trajectory_length}")

    return result


async def test_manual_rewind(safety_monitor: SafetyMonitor):
    """Test manual rewind with configured percentage."""
    print(f"\n=== Testing Manual Rewind ({safety_monitor.manual_rewind_percentage}%) ===\n")

    initial_len = safety_monitor._rewind_mgr.trajectory_length
    print(f"Initial trajectory length: {initial_len}")

    result = await safety_monitor.trigger_manual_rewind()

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Steps rewound: {result.steps_rewound}")
    if result.error:
        print(f"  Error: {result.error}")

    print(f"\nTrajectory length after rewind: {safety_monitor._rewind_mgr.trajectory_length}")

    return result


async def test_boundary_detection(rewind_mgr: RewindManager, base_backend: MockBaseBackend):
    """Test out-of-bounds detection."""
    print(f"\n=== Testing Boundary Detection ===\n")

    # Get safety config
    safety_cfg = rewind_mgr._safety._cfg
    print(f"Workspace boundaries:")
    print(f"  X: [{safety_cfg.base_workspace_min[0]}, {safety_cfg.base_workspace_max[0]}]")
    print(f"  Y: [{safety_cfg.base_workspace_min[1]}, {safety_cfg.base_workspace_max[1]}]")

    # Test inside bounds
    base_backend.current_pose = [0.0, 0.0, 0.0]
    status = rewind_mgr.get_base_boundary_status()
    print(f"\nPosition (0, 0): out_of_bounds = {status['out_of_bounds']}")

    # Test at boundary
    base_backend.current_pose = [4.9, 4.9, 0.0]
    status = rewind_mgr.get_base_boundary_status()
    print(f"Position (4.9, 4.9): out_of_bounds = {status['out_of_bounds']}")

    # Test outside bounds
    base_backend.current_pose = [6.0, 0.0, 0.0]
    status = rewind_mgr.get_base_boundary_status()
    print(f"Position (6.0, 0): out_of_bounds = {status['out_of_bounds']}")

    # Test negative outside bounds
    base_backend.current_pose = [-6.0, -6.0, 0.0]
    status = rewind_mgr.get_base_boundary_status()
    print(f"Position (-6, -6): out_of_bounds = {status['out_of_bounds']}")


async def test_dry_run(rewind_mgr: RewindManager):
    """Test dry-run mode (preview without executing)."""
    print(f"\n=== Testing Dry-Run Mode ===\n")

    initial_len = rewind_mgr.trajectory_length
    print(f"Trajectory length before: {initial_len}")

    result = await rewind_mgr.rewind_percentage(50.0, dry_run=True)

    print(f"\nDry-run result:")
    print(f"  Would rewind: {result.steps_rewound} steps")
    print(f"  From waypoint {result.start_waypoint_idx} to {result.end_waypoint_idx}")

    print(f"\nTrajectory length after dry-run: {rewind_mgr.trajectory_length}")
    print(f"(Should be unchanged: {initial_len == rewind_mgr.trajectory_length})")


async def main():
    print("=" * 60)
    print("REWIND FUNCTIONALITY TEST")
    print("=" * 60)

    # Create mock backend
    base_backend = MockBaseBackend()

    # Create trajectory recorder
    trajectory = TrajectoryRecorder(max_length=1000)

    # Create safety envelope
    safety_cfg = SafetyConfig()
    safety = SafetyEnvelope(safety_cfg)

    # Create rewind manager with fast settle times for testing
    rewind_cfg = RewindConfig(
        base_settle_time=0.1,
        manual_rewind_percentage=20.0,  # 20% for manual rewind
        auto_rewind_percentage=10.0,    # 10% for auto rewind
    )

    rewind_mgr = RewindManager(
        trajectory=trajectory,
        safety=safety,
        base_backend=base_backend,
        config=rewind_cfg,
    )

    # Create safety monitor
    safety_monitor = SafetyMonitor(rewind_mgr)

    # Test 1: Boundary detection
    await test_boundary_detection(rewind_mgr, base_backend)

    # Test 2: Create trajectory and test dry-run
    create_test_trajectory(trajectory, n_waypoints=10)
    await test_dry_run(rewind_mgr)

    # Test 3: Manual rewind (20%)
    await test_manual_rewind(safety_monitor)

    # Test 4: Recreate trajectory and test percentage rewind
    trajectory._waypoints.clear()
    create_test_trajectory(trajectory, n_waypoints=20)
    await test_rewind_percentage(rewind_mgr, 30.0)

    # Test 5: Reset to home (100%)
    trajectory._waypoints.clear()
    create_test_trajectory(trajectory, n_waypoints=15)
    await test_reset_to_home(safety_monitor)

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"\nBase move history: {len(base_backend.move_history)} moves")
    print(f"Arm move history: {len(franka_backend.move_history)} moves")
    print(f"Gripper move history: {len(gripper_backend.move_history)} moves")
    print(f"\nFinal trajectory length: {len(trajectory)}")
    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
