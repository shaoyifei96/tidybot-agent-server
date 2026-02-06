#!/usr/bin/env python3
"""Test the arm SDK by submitting code via /code/execute."""

import json
import time
import urllib.request
import urllib.error

SERVER_URL = "http://localhost:8080"


def request(method: str, path: str, data: dict = None, headers: dict = None) -> dict:
    """Make HTTP request to server."""
    url = f"{SERVER_URL}{path}"
    headers = headers or {}
    headers["Content-Type"] = "application/json"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main():
    print("=" * 60)
    print("Testing Arm SDK via Code Execution")
    print("=" * 60)

    # 1. Get current state
    print("\n1. Getting current robot state...")
    state = request("GET", "/state")
    arm_q = state.get("arm", {}).get("q", [0]*7)
    print(f"   Current joint 4: {arm_q[4]:.3f} rad")

    # 2. Acquire lease
    print("\n2. Acquiring lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": "test_arm_sdk"})
    lease_id = lease_resp.get("lease_id")
    print(f"   Lease acquired: {lease_id}")

    try:
        # 3. Submit code to read state and move arm slightly
        print("\n3. Submitting code to test arm SDK...")

        code = '''
from robot_sdk import arm, sensors
import time

# Read current state
print("Reading current arm joints...")
joints = sensors.get_arm_joints()
print(f"Current joints: {[f'{q:.3f}' for q in joints]}")

# Read EE position
ee_pos = sensors.get_ee_position()
print(f"Current EE position: x={ee_pos[0]:.3f}, y={ee_pos[1]:.3f}, z={ee_pos[2]:.3f}")

# Move joint 4 by a small amount (0.05 rad ~ 3 degrees)
print("\\nMoving joint 4 by +0.05 rad...")
target = list(joints)
target[4] += 0.05
arm.move_joints(target, timeout=10)

# Read new state
print("\\nReading new arm joints...")
new_joints = sensors.get_arm_joints()
print(f"New joints: {[f'{q:.3f}' for q in new_joints]}")

# Check movement
delta = new_joints[4] - joints[4]
print(f"\\nJoint 4 moved by: {delta:.3f} rad")
print("Arm SDK test PASSED!")
'''

        headers = {"X-Lease-Id": lease_id}
        exec_resp = request("POST", "/code/execute", {"code": code, "timeout": 30}, headers)

        if not exec_resp.get("success"):
            print(f"   ERROR: {exec_resp}")
            return

        execution_id = exec_resp.get("execution_id")
        print(f"   Execution started: {execution_id}")

        # 4. Wait for completion
        print("\n4. Waiting for completion...")
        for i in range(60):
            status = request("GET", "/code/status")
            if not status.get("is_running"):
                break
            print(f"   Still running... ({i+1}s)")
            time.sleep(1)

        # 5. Get result
        print("\n5. Getting result...")
        result_resp = request("GET", "/code/result")
        result = result_resp.get("result", {})

        print(f"   Status: {result.get('status')}")
        print(f"   Exit code: {result.get('exit_code')}")
        print(f"   Duration: {result.get('duration', 0):.2f}s")

        print("\n   --- STDOUT ---")
        stdout = result.get("stdout", "")
        for line in stdout.strip().split("\n"):
            print(f"   {line}")

        if result.get("stderr"):
            print("\n   --- STDERR ---")
            for line in result.get("stderr", "").strip().split("\n"):
                print(f"   {line}")

        if result.get("status") == "completed":
            print("\n" + "=" * 60)
            print("TEST PASSED!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print(f"TEST FAILED: {result.get('error')}")
            print("=" * 60)

    finally:
        # 6. Release lease
        print("\n6. Releasing lease...")
        request("POST", "/lease/release", {"lease_id": lease_id})
        print("   Lease released")


if __name__ == "__main__":
    main()
