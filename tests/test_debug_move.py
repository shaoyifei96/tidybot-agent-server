#!/usr/bin/env python3
"""Debug test - simpler movements with verbose output."""

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
    print("=" * 60)
    print("Debug Movement Test")
    print("=" * 60)

    # Acquire lease
    print("\n1. Acquiring lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": "debug_test"})
    lease_id = lease_resp.get("lease_id")
    print(f"   Lease: {lease_id}")

    try:
        print("\n2. Submitting debug code...")

        code = '''
from robot_sdk import arm, sensors, rewind
import math
import time

print("=== DEBUG MOVEMENT TEST ===")

# Initial state
print("\\n--- Initial State ---")
base_pose = sensors.get_base_pose()
arm_joints = sensors.get_arm_joints()
print(f"Base: x={base_pose[0]:.4f}, y={base_pose[1]:.4f}, theta={base_pose[2]:.4f}")
print(f"Arm J0: {arm_joints[0]:.4f} rad ({math.degrees(arm_joints[0]):.2f} deg)")

# Just move the arm (should work)
print("\\n--- Moving Arm Joint 0 by +45 deg ---")
target_joints = list(arm_joints)
target_joints[0] += math.pi / 4  # +45 degrees
print(f"Target J0: {target_joints[0]:.4f} rad ({math.degrees(target_joints[0]):.2f} deg)")

arm.move_joints(target_joints, timeout=15)

print("\\n--- After Arm Move ---")
new_joints = sensors.get_arm_joints()
print(f"Arm J0: {new_joints[0]:.4f} rad ({math.degrees(new_joints[0]):.2f} deg)")
print(f"Delta: {math.degrees(new_joints[0] - arm_joints[0]):.2f} deg")

# Wait a bit for trajectory to record
time.sleep(1)

# Check trajectory
status = rewind.get_status()
print(f"\\nTrajectory length: {status['trajectory_length']}")

# Now rewind
print("\\n--- REWINDING ---")
result = rewind.reset_to_home()
print(f"Success: {result.success}")
print(f"Steps rewound: {result.steps_rewound}")
print(f"Error: {result.error}")

# Final state
print("\\n--- Final State ---")
final_joints = sensors.get_arm_joints()
print(f"Arm J0: {final_joints[0]:.4f} rad ({math.degrees(final_joints[0]):.2f} deg)")

print("\\n=== DONE ===")
'''

        headers = {"X-Lease-Id": lease_id}
        exec_resp = request("POST", "/code/execute", {"code": code, "timeout": 120}, headers)

        if not exec_resp.get("success"):
            print(f"   ERROR: {exec_resp}")
            return

        execution_id = exec_resp.get("execution_id")
        print(f"   Execution started: {execution_id}")

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
        print(f"   Duration: {result.get('duration', 0):.2f}s")

        print("\n" + "=" * 50)
        print("STDOUT:")
        print("=" * 50)
        print(result.get("stdout", ""))

        if result.get("stderr"):
            print("=" * 50)
            print("STDERR:")
            print("=" * 50)
            print(result.get("stderr", ""))

    finally:
        print("\n5. Releasing lease...")
        request("POST", "/lease/release", {"lease_id": lease_id})
        print("   Done")


if __name__ == "__main__":
    main()
