#!/usr/bin/env python3
"""Test base movement with velocity commands."""

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
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main():
    print("=" * 50)
    print("Base Velocity Test")
    print("=" * 50)

    # Acquire lease
    print("\n1. Acquiring lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": "base_vel_test"})
    lease_id = lease_resp.get("lease_id")
    print(f"   Lease: {lease_id}")
    headers = {"X-Lease-Id": lease_id}

    try:
        # Get initial state
        state = request("GET", "/state")
        base_pose = state.get("base", {}).get("pose", [0, 0, 0])
        print(f"\n2. Initial base pose: x={base_pose[0]:.4f}, y={base_pose[1]:.4f}")

        # Send velocity command to move in -Y direction
        print("\n3. Sending velocity command (vy=-0.1 m/s for 2 seconds)...")
        request("POST", "/cmd/base/move", {"vx": 0, "vy": -0.1, "wz": 0, "frame": "local"}, headers)

        # Monitor position for 3 seconds
        for i in range(6):
            time.sleep(0.5)
            state = request("GET", "/state")
            base_pose = state.get("base", {}).get("pose", [0, 0, 0])
            print(f"   t={0.5*(i+1):.1f}s: x={base_pose[0]:.4f}, y={base_pose[1]:.4f}")

        # Stop
        print("\n4. Stopping base...")
        request("POST", "/cmd/base/stop", {}, headers)

        # Final state
        state = request("GET", "/state")
        base_pose = state.get("base", {}).get("pose", [0, 0, 0])
        print(f"\n5. Final base pose: x={base_pose[0]:.4f}, y={base_pose[1]:.4f}")

    finally:
        print("\n6. Releasing lease...")
        request("POST", "/lease/release", {"lease_id": lease_id})
        print("   Done")


if __name__ == "__main__":
    main()
