#!/usr/bin/env python3
"""Test lease queue by submitting 3 jobs with different holders.

Each job acquires its own lease (queues if busy), runs code, then releases.
Each job: move +x 0.5m, move -y 0.5m, rotate 40 deg clockwise.
"""

import json
import threading
import time
import urllib.request
import urllib.error

SERVER_URL = "http://localhost:8080"
LOG_LOCK = threading.Lock()


def log(job: str, msg: str):
    with LOG_LOCK:
        print(f"  [{job:>7s}] {msg}")


def request(method: str, path: str, data: dict = None, headers: dict = None, timeout: float = 300) -> dict:
    url = f"{SERVER_URL}{path}"
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            return {"_http_error": e.code, **json.loads(body_text)}
        except json.JSONDecodeError:
            return {"_http_error": e.code, "detail": body_text}


MOVE_CODE = '''
from robot_sdk import base, sensors

JOB = "{job_name}"
print(f"=== Job {{JOB}} starting ===")

pose = sensors.get_base_pose()
print(f"Start: x={{pose[0]:.3f}}, y={{pose[1]:.3f}}, theta={{pose[2]:.3f}}")

print("Moving +x 0.5m...")
base.move_delta(dx=0.5, frame="local")

print("Moving -y 0.5m...")
base.move_delta(dy=-0.5, frame="local")

print("Rotating 40 deg CW...")
base.rotate_degrees(-40)

pose = sensors.get_base_pose()
print(f"End:   x={{pose[0]:.3f}}, y={{pose[1]:.3f}}, theta={{pose[2]:.3f}}")
print(f"=== Job {{JOB}} complete ===")
'''


def run_job(job_name: str, results: dict):
    """One job: acquire lease -> submit code -> wait -> release."""
    t0 = time.time()

    # 1. Acquire lease (blocks until granted)
    log(job_name, "Requesting lease...")
    lease_resp = request("POST", "/lease/acquire", {"holder": job_name})
    if "_http_error" in lease_resp:
        log(job_name, f"Lease error: {lease_resp}")
        results[job_name] = {"ok": False, "error": str(lease_resp)}
        return

    lease_id = lease_resp["lease_id"]
    wait_time = time.time() - t0
    log(job_name, f"Lease granted (waited {wait_time:.1f}s): {lease_id[:8]}...")

    try:
        # 2. Submit code
        code = MOVE_CODE.format(job_name=job_name)
        headers = {"X-Lease-Id": lease_id}
        exec_resp = request("POST", "/code/execute", {"code": code, "timeout": 120}, headers)

        if "_http_error" in exec_resp or not exec_resp.get("success"):
            err = exec_resp.get("detail", exec_resp.get("message", str(exec_resp)))
            log(job_name, f"Execute failed: {err}")
            results[job_name] = {"ok": False, "error": err}
            return

        log(job_name, f"Code submitted: {exec_resp['execution_id']}")

        # 3. Wait for completion
        for _ in range(240):
            status = request("GET", "/code/status")
            if not status.get("is_running"):
                break
            time.sleep(0.5)

        # 4. Get result
        result = request("GET", "/code/result").get("result", {})
        log(job_name, f"Finished: {result.get('status')} ({result.get('duration', 0):.1f}s)")

        # Print stdout (skip SDK init lines)
        for line in result.get("stdout", "").strip().split("\n"):
            if not line.startswith("[SDK]"):
                log(job_name, line)

        if result.get("stderr"):
            for line in result.get("stderr", "").strip().split("\n")[-3:]:
                log(job_name, f"STDERR: {line}")

        results[job_name] = {"ok": result.get("status") == "completed", "duration": result.get("duration", 0)}

    finally:
        # 5. Release lease
        log(job_name, "Releasing lease...")
        request("POST", "/lease/release", {"lease_id": lease_id})
        total = time.time() - t0
        log(job_name, f"Done (total {total:.1f}s)")


def main():
    print("=" * 60)
    print("  Queue Test: 3 Jobs (+x 0.5m, -y 0.5m, rotate -40 deg)")
    print("  Each job acquires its own lease and queues if busy")
    print("=" * 60)
    print()

    job_names = ["alpha", "bravo", "charlie"]
    results = {}
    threads = []

    # Launch all 3 jobs concurrently
    for name in job_names:
        t = threading.Thread(target=run_job, args=(name, results))
        threads.append(t)

    t0 = time.time()
    for t in threads:
        t.start()
        time.sleep(0.2)  # slight stagger so order is deterministic

    # Wait for all to finish
    for t in threads:
        t.join()

    total = time.time() - t0

    # Summary
    print()
    print("=" * 60)
    print(f"  Summary (total {total:.1f}s)")
    print("=" * 60)
    for name in job_names:
        r = results.get(name, {})
        status = "OK" if r.get("ok") else "FAIL"
        dur = r.get("duration", 0)
        err = r.get("error", "")
        extra = f" ({dur:.1f}s)" if dur else f" - {err}" if err else ""
        print(f"  [{name:>7s}] {status}{extra}")


if __name__ == "__main__":
    main()
