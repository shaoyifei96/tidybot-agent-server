#!/usr/bin/env python3
"""Move base and arm, then rewind."""

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
    print("Move Base + Arm, Then Rewind")
    print("=" * 60)

    # Get initial state
    print("\n1. Getting initial state...")
    state = request("GET", "/state")
    base_pose = state.get("base", {}).get("pose", [0, 0, 0])
    arm_q = state.get("arm", {}).get("q", [0]*7)
    print(f"   Base: x={base_pose[0]:.3f}, y={base_pose[1]:.3f}, theta={base_pose[2]:.3f}")
    print(f"   Arm joint 0: {arm_q[0]:.3f} rad ({arm_q[0]*180/3.14159:.1f} deg)")

    # Check lease queue before acquiring
    print("\n2. Checking lease status before acquiring...")
    lease_status = request("GET", "/lease/status")
    holder = lease_status.get("holder")
    queue = lease_status.get("queue", [])
    print(f"   Current holder: {holder if holder else '(none)'}")
    if lease_status.get("lease_id"):
        print(f"   Lease ID: {lease_status['lease_id']}")
    if lease_status.get("expires_at"):
        print(f"   Expires at: {lease_status['expires_at']}")
    if queue:
        print(f"   Queue ({len(queue)} waiting):")
        for i, entry in enumerate(queue):
            print(f"     [{i}] {entry}")
    else:
        print("   Queue: (empty)")

    # Acquire lease
    print("\n3. Acquiring lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": "move_and_rewind"})
    lease_id = lease_resp.get("lease_id")
    print(f"   Lease: {lease_id}")

    try:
        # Submit code to move base and arm
        print("\n4. Submitting movement code...")

        code = '''
from robot_sdk import base, arm, sensors, rewind
import math
import time

# Get initial state
print("=== Initial State ===")
base_pose = sensors.get_base_pose()
arm_joints = sensors.get_arm_joints()
print(f"Base: x={base_pose[0]:.3f}, y={base_pose[1]:.3f}")
print(f"Arm joint 0: {arm_joints[0]:.3f} rad ({math.degrees(arm_joints[0]):.1f} deg)")

# Check trajectory before moves
status = rewind.get_status()
print(f"\\nTrajectory length before: {status['trajectory_length']}")

# Move base in negative y by 0.2m
print("\\n=== Moving base -0.2m in Y ===")
base.move_delta(dy=-0.2, frame="local")
time.sleep(0.5)

# Read state after base move
base_pose2 = sensors.get_base_pose()
print(f"Base after: x={base_pose2[0]:.3f}, y={base_pose2[1]:.3f}")
print(f"Base moved: dy={base_pose2[1] - base_pose[1]:.3f}m")

# Move arm joint 0 by 45 degrees (pi/4 radians)
print("\\n=== Moving arm joint 0 by +45 deg ===")
target_joints = list(arm_joints)
target_joints[0] += math.pi / 4  # +45 degrees
arm.move_joints(target_joints, timeout=30)
time.sleep(0.5)

# Read state after arm move
arm_joints2 = sensors.get_arm_joints()
print(f"Arm joint 0 after: {arm_joints2[0]:.3f} rad ({math.degrees(arm_joints2[0]):.1f} deg)")
print(f"Arm moved: {math.degrees(arm_joints2[0] - arm_joints[0]):.1f} deg")

# Check trajectory after moves
status = rewind.get_status()
print(f"\\nTrajectory length after moves: {status['trajectory_length']}")

# Now rewind!
print("\\n=== REWINDING ===")
result = rewind.reset_to_home()
print(f"Rewind success: {result.success}")
print(f"Steps rewound: {result.steps_rewound}")
print(f"Components: {result.components_rewound}")
if result.error:
    print(f"Error: {result.error}")

# Read final state
print("\\n=== Final State ===")
base_pose3 = sensors.get_base_pose()
arm_joints3 = sensors.get_arm_joints()
print(f"Base: x={base_pose3[0]:.3f}, y={base_pose3[1]:.3f}")
print(f"Arm joint 0: {arm_joints3[0]:.3f} rad ({math.degrees(arm_joints3[0]):.1f} deg)")

# Summary
print("\\n=== Summary ===")
print(f"Base Y: {base_pose[1]:.3f} -> {base_pose2[1]:.3f} -> {base_pose3[1]:.3f}")
print(f"Arm J0: {math.degrees(arm_joints[0]):.1f} -> {math.degrees(arm_joints2[0]):.1f} -> {math.degrees(arm_joints3[0]):.1f} deg")
'''

        headers = {"X-Lease-Id": lease_id}
        exec_resp = request("POST", "/code/execute", {"code": code, "timeout": 120}, headers)

        if not exec_resp.get("success"):
            print(f"   ERROR: {exec_resp}")
            return

        execution_id = exec_resp.get("execution_id")
        print(f"   Execution started: {execution_id}")

        # Wait for completion
        print("\n5. Waiting for completion...")
        for i in range(120):
            status = request("GET", "/code/status")
            if not status.get("is_running"):
                break
            if i % 5 == 0:
                print(f"   Running... ({i}s)")
            time.sleep(1)

        # Get result
        print("\n6. Result:")
        result_resp = request("GET", "/code/result")
        result = result_resp.get("result", {})

        print(f"   Status: {result.get('status')}")
        print(f"   Duration: {result.get('duration', 0):.2f}s")

        print("\n" + "-" * 50)
        print("STDOUT:")
        print("-" * 50)
        print(result.get("stdout", ""))

        if result.get("stderr"):
            print("-" * 50)
            print("STDERR:")
            print("-" * 50)
            print(result.get("stderr", ""))

    finally:
        print("\n7. Releasing lease...")
        request("POST", "/lease/release", {"lease_id": lease_id})
        print("   Done")


if __name__ == "__main__":
    main()
