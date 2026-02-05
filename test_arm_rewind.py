#!/usr/bin/env python3
"""Test arm movement and rewind (without base)."""

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
    print("Arm Movement + Rewind Test")
    print("=" * 50)

    # Acquire lease
    print("\n1. Acquiring lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": "arm_rewind_test"})
    lease_id = lease_resp.get("lease_id")
    print(f"   Lease: {lease_id}")

    try:
        print("\n2. Submitting arm movement code...")

        code = '''
from robot_sdk import arm, sensors, rewind
import math
import time

print("=== ARM + REWIND TEST ===")

# Initial state
print("\\n--- Initial State ---")
joints = sensors.get_arm_joints()
print(f"Arm J0: {joints[0]:.3f} rad ({math.degrees(joints[0]):.1f} deg)")

status = rewind.get_status()
print(f"Trajectory length: {status['trajectory_length']}")

# Clear trajectory for clean test
print("\\nClearing trajectory...")
rewind.clear_trajectory()
time.sleep(0.5)

status = rewind.get_status()
print(f"Trajectory length after clear: {status['trajectory_length']}")

# Move arm joint 0 by +30 degrees (smaller, safer movement)
print("\\n--- Moving Arm J0 by +30 deg ---")
target = list(joints)
target[0] += math.radians(30)
print(f"Target J0: {target[0]:.3f} rad ({math.degrees(target[0]):.1f} deg)")

arm.move_joints(target, timeout=20)

joints2 = sensors.get_arm_joints()
print(f"After move J0: {joints2[0]:.3f} rad ({math.degrees(joints2[0]):.1f} deg)")
print(f"Moved: {math.degrees(joints2[0] - joints[0]):.1f} deg")

# Wait for trajectory to record
time.sleep(1)
status = rewind.get_status()
print(f"\\nTrajectory length after move: {status['trajectory_length']}")

# Rewind
print("\\n--- REWINDING ---")
result = rewind.reset_to_home()
print(f"Success: {result.success}")
print(f"Steps rewound: {result.steps_rewound}")
if result.error:
    print(f"Error: {result.error}")

# Final state
joints3 = sensors.get_arm_joints()
print(f"\\n--- Final State ---")
print(f"Arm J0: {joints3[0]:.3f} rad ({math.degrees(joints3[0]):.1f} deg)")

# Summary
print(f"\\n=== SUMMARY ===")
print(f"J0: {math.degrees(joints[0]):.1f} -> {math.degrees(joints2[0]):.1f} -> {math.degrees(joints3[0]):.1f} deg")
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
            if i % 10 == 0:
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
