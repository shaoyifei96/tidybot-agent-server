#!/usr/bin/env python3
"""Test lease manager functionality."""

import asyncio
import sys
from lease import LeaseManager
from config import LeaseConfig


async def test_lease_status_visibility():
    """Test that queue is visible and lease_id is hidden in status."""
    print("=" * 60)
    print("TEST: Lease Status Visibility")
    print("=" * 60)

    # Create lease manager with short timeouts for testing
    config = LeaseConfig(
        idle_timeout_s=5.0,
        warning_grace_s=2.0,
        max_duration_s=30.0,
        check_interval_s=1.0,
    )

    def last_moved_at():
        return 0.0

    lease_mgr = LeaseManager(config, last_moved_at)
    await lease_mgr.start()

    try:
        # Test 1: Empty status
        print("\n[Test 1] Initial status (no holder):")
        status = lease_mgr.status()
        print(f"  Status: {status}")
        assert status["holder"] is None
        assert status["queue_length"] == 0
        assert status["queue"] == []
        assert "lease_id" not in status, "❌ lease_id should NOT be in empty status"
        print("  ✓ Empty status correct")

        # Test 2: Acquire lease
        print("\n[Test 2] Acquire lease (alice):")
        result = await lease_mgr.acquire("alice")
        print(f"  Acquire result: {result}")
        assert result["status"] == "granted"
        assert "lease_id" in result, "❌ lease_id should be in acquire response"
        alice_lease_id = result["lease_id"]
        print(f"  ✓ Alice got lease: {alice_lease_id}")

        # Test 3: Status with current holder
        print("\n[Test 3] Status with current holder:")
        status = lease_mgr.status()
        print(f"  Status: {status}")
        assert status["holder"] == "alice"
        assert status["queue_length"] == 0
        assert status["queue"] == []
        assert "lease_id" not in status, "❌ lease_id should NOT be in public status!"
        print("  ✓ Status hides lease_id (security fix works!)")

        # Test 4: Queue multiple holders
        print("\n[Test 4] Queue multiple holders:")
        # Start acquire tasks that will block
        bob_task = asyncio.create_task(lease_mgr.acquire("bob"))
        await asyncio.sleep(0.1)  # Let bob enter queue

        charlie_task = asyncio.create_task(lease_mgr.acquire("charlie"))
        await asyncio.sleep(0.1)  # Let charlie enter queue

        status = lease_mgr.status()
        print(f"  Status: {status}")
        assert status["holder"] == "alice"
        assert status["queue_length"] == 2
        assert len(status["queue"]) == 2
        assert status["queue"][0] == {"position": 1, "holder": "bob"}
        assert status["queue"][1] == {"position": 2, "holder": "charlie"}
        assert "lease_id" not in status
        print("  ✓ Queue visible with positions")

        # Test 5: Re-acquire (get lease_id reminder)
        print("\n[Test 5] Re-acquire existing lease:")
        result = await lease_mgr.acquire("alice")
        print(f"  Re-acquire result: {result}")
        assert result["status"] == "already_held"
        assert result["lease_id"] == alice_lease_id
        print("  ✓ Holder can re-acquire to get lease_id reminder")

        # Test 6: Release and queue progression
        print("\n[Test 6] Release and queue progression:")
        release_result = await lease_mgr.release(alice_lease_id)
        print(f"  Release result: {release_result}")
        assert release_result["status"] == "released"

        # Wait for bob to get the lease
        bob_result = await asyncio.wait_for(bob_task, timeout=1.0)
        print(f"  Bob's result: {bob_result}")
        assert bob_result["status"] == "granted"
        assert "lease_id" in bob_result

        status = lease_mgr.status()
        print(f"  Status after release: {status}")
        assert status["holder"] == "bob"
        assert status["queue_length"] == 1
        assert status["queue"][0] == {"position": 1, "holder": "charlie"}
        assert "lease_id" not in status
        print("  ✓ Queue progresses correctly")

        # Clean up
        charlie_task.cancel()
        try:
            await charlie_task
        except asyncio.CancelledError:
            pass

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        print("\nSummary:")
        print("  ✓ lease_id hidden from public status endpoint")
        print("  ✓ Queue shows holder names and positions")
        print("  ✓ Holders can re-acquire to get their lease_id")
        print("  ✓ Queue progression works correctly")

    finally:
        await lease_mgr.stop()


async def main():
    try:
        await test_lease_status_visibility()
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
