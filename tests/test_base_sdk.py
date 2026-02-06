#!/usr/bin/env python3
"""Test the base SDK by submitting code via /code/execute."""

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
    print("Testing Base SDK via Code Execution")
    print("=" * 60)

    # 1. Get current state
    print("\n1. Getting current robot state...")
    state = request("GET", "/state")
    base_pose = state.get("base", {}).get("pose", [0, 0, 0])
    print(f"   Current base pose: x={base_pose[0]:.3f}, y={base_pose[1]:.3f}, theta={base_pose[2]:.3f}")

    # 2. Acquire lease
    print("\n2. Acquiring lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": "test_base_sdk"})
    lease_id = lease_resp.get("lease_id")
    print(f"   Lease acquired: {lease_id}")

    try:
        # 3. Submit code to read state and move base slightly
        print("\n3. Submitting code to test base SDK...")

        code = '''
from robot_sdk import base, sensors
import time

# Read current state
print("Reading current base pose...")
pose = sensors.get_base_pose()
print(f"Current pose: x={pose[0]:.3f}, y={pose[1]:.3f}, theta={pose[2]:.3f}")

# Move base forward by 5cm (small safe movement)
print("\\nMoving base forward by 0.05m...")
base.move_delta(dx=0.05, frame="local")

# Read new state
print("\\nReading new base pose...")
new_pose = sensors.get_base_pose()
print(f"New pose: x={new_pose[0]:.3f}, y={new_pose[1]:.3f}, theta={new_pose[2]:.3f}")

# Calculate movement
dx = new_pose[0] - pose[0]
dy = new_pose[1] - pose[1]
import math
dist = math.sqrt(dx*dx + dy*dy)
print(f"\\nMoved distance: {dist:.3f}m")
print("Base SDK test PASSED!")
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
        for i in range(60):  # Wait up to 60 seconds
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
