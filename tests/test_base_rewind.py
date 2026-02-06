#!/usr/bin/env python3
"""Test base movement (-0.2m Y) and rewind."""

import json
import time
import urllib.request

SERVER_URL = "http://localhost:8080"


def request(method: str, path: str, data: dict = None, headers: dict = None) -> dict:
    url = f"{SERVER_URL}{path}"
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main():
    print("=" * 50)
    print("Base Move (-0.2m Y) + Rewind Test")
    print("=" * 50)

    # Acquire lease
    print("\n1. Acquiring lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": "base_rewind_test"})
    lease_id = lease_resp.get("lease_id")
    print(f"   Lease: {lease_id}")

    try:
        print("\n2. Submitting base movement + rewind code...")

        code = '''
from robot_sdk import base, sensors, rewind
import math
import time

print("=== BASE MOVE + REWIND TEST ===")

# Initial state
print("\\n--- Initial State ---")
pose = sensors.get_base_pose()
print(f"Base: x={pose[0]:.3f}, y={pose[1]:.3f}, theta={pose[2]:.3f}")

status = rewind.get_status()
print(f"Trajectory length: {status['trajectory_length']}")

# Clear trajectory for clean test
print("\\nClearing trajectory...")
rewind.clear_trajectory()
time.sleep(0.5)

status = rewind.get_status()
print(f"Trajectory length after clear: {status['trajectory_length']}")

# Move base -0.2m in Y (local frame)
print("\\n--- Moving base -0.2m in Y ---")
base.move_delta(dy=-0.2, frame="local")
time.sleep(1.0)

# Read state after move
pose2 = sensors.get_base_pose()
print(f"Base after move: x={pose2[0]:.3f}, y={pose2[1]:.3f}, theta={pose2[2]:.3f}")
dy = pose2[1] - pose[1]
print(f"Moved: dy={dy:.3f}m")

# Check trajectory
status = rewind.get_status()
print(f"\\nTrajectory length after move: {status['trajectory_length']}")

# Rewind
print("\\n--- REWINDING ---")
result = rewind.reset_to_home()
print(f"Success: {result.success}")
print(f"Steps rewound: {result.steps_rewound}")
print(f"Components: {result.components_rewound}")
if result.error:
    print(f"Error: {result.error}")

time.sleep(0.5)

# Final state
pose3 = sensors.get_base_pose()
print(f"\\n--- Final State ---")
print(f"Base: x={pose3[0]:.3f}, y={pose3[1]:.3f}, theta={pose3[2]:.3f}")

# Summary
print(f"\\n=== SUMMARY ===")
print(f"Y position: {pose[1]:.3f} -> {pose2[1]:.3f} -> {pose3[1]:.3f}")
print(f"Recovery error: {abs(pose3[1] - pose[1]):.3f}m")
print("=== DONE ===")
'''

        headers = {"X-Lease-Id": lease_id}
        exec_resp = request("POST", "/code/execute", {"code": code, "timeout": 120}, headers)

        if not exec_resp.get("success"):
            print(f"   ERROR: {exec_resp}")
            return

        print(f"   Execution started: {exec_resp.get('execution_id')}")

        # Wait for completion
        print("\n3. Waiting...")
        for i in range(120):
            status = request("GET", "/code/status")
            if not status.get("is_running"):
                break
            if i % 5 == 0:
                print(f"   Running... ({i}s)")
            time.sleep(1)

        # Get result
        print("\n4. Result:")
        result_resp = request("GET", "/code/result")
        result = result_resp.get("result", {})

        print(f"   Status: {result.get('status')}")
        print(f"   Duration: {result.get('duration', 0):.1f}s")

        print("\n" + "=" * 50)
        print("OUTPUT:")
        print("=" * 50)
        print(result.get("stdout", ""))

        if result.get("stderr"):
            print("=" * 50)
            print("ERRORS:")
            print("=" * 50)
            print(result.get("stderr", ""))

    finally:
        print("\n5. Releasing lease...")
        request("POST", "/lease/release", {"lease_id": lease_id})
        print("   Done")


if __name__ == "__main__":
    main()
