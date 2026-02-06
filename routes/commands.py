"""POST /cmd/* endpoints — command dispatch with lease + safety checks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/cmd", include_in_schema=False)


# -- request models ----------------------------------------------------------

class BaseMoveRequest(BaseModel):
    # Position mode
    x: Optional[float] = None
    y: Optional[float] = None
    theta: Optional[float] = None
    # Velocity mode
    vx: Optional[float] = None
    vy: Optional[float] = None
    wz: Optional[float] = None
    frame: str = "global"


class ArmMoveRequest(BaseModel):
    mode: str  # joint_position, cartesian_pose, joint_velocity, cartesian_velocity
    values: list[float]


class GripperRequest(BaseModel):
    action: str  # activate, move, open, close, stop, calibrate, grasp
    # Raw mode (Robotiq-style, 0-255)
    position: Optional[int] = None  # 0-255 (0=open, 255=closed)
    speed: int = 255                # 0-255
    force: int = 255                # 0-255
    # Calibrated mode (Franka-style, backwards compat)
    width: Optional[float] = None   # meters


class ResetRequest(BaseModel):
    fraction: float = 1.0


# -- helpers -----------------------------------------------------------------

def _reject(cmd_id: str, reason: str, detail: str = ""):
    return JSONResponse(
        {"type": "cmd_rejected", "cmd_id": cmd_id, "reason": reason, "detail": detail},
        status_code=400,
    )


def _check_lease(lease_mgr, lease_id: str | None, cmd_id: str):
    if not lease_id:
        return _reject(cmd_id, "no_lease", "X-Lease-Id header required")
    if not lease_mgr.validate_lease(lease_id):
        return _reject(cmd_id, "invalid_lease", "lease not valid or expired")
    lease_mgr.record_command()
    return None


def _check_base(base_backend, cmd_id: str):
    if not base_backend.is_connected:
        return _reject(cmd_id, "backend_unavailable", "base backend not connected")
    return None


def _check_franka(franka_backend, cmd_id: str):
    if not franka_backend.is_connected:
        return _reject(cmd_id, "backend_unavailable", "franka backend not connected")
    return None


def _check_gripper(gripper_backend, cmd_id: str):
    if not gripper_backend.is_connected:
        return _reject(cmd_id, "backend_unavailable", "gripper backend not connected")
    return None


# -- router factory ----------------------------------------------------------

logger = logging.getLogger(__name__)


def create_router(lease_mgr, safety, base_backend, franka_backend, gripper_backend, feedback_fn, state_agg, system_logger):
    """feedback_fn(event_dict) broadcasts to operator's /ws/feedback."""

    @router.post("/base/move")
    async def base_move(req: BaseMoveRequest, x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
        if err:
            return err
        err = _check_base(base_backend, cmd_id)
        if err:
            return err

        feedback_fn({"type": "cmd_ack", "cmd_id": cmd_id, "status": "accepted"})

        if req.vx is not None or req.vy is not None or req.wz is not None:
            vx, vy, wz = req.vx or 0, req.vy or 0, req.wz or 0
            check = safety.check_base_velocity(vx, vy, wz)
            if not check.ok:
                return _reject(cmd_id, check.reason, check.detail)
            base_backend.set_target_velocity(vx, vy, wz, req.frame)
        else:
            x, y, theta = req.x or 0, req.y or 0, req.theta or 0
            check = safety.check_base_pose(x, y, theta)
            if not check.ok:
                return _reject(cmd_id, check.reason, check.detail)
            base_backend.execute_action(x, y, theta)

        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": "completed"})
        return {"cmd_id": cmd_id, "status": "completed"}

    @router.post("/base/stop")
    async def base_stop(x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
        if err:
            return err
        err = _check_base(base_backend, cmd_id)
        if err:
            return err
        base_backend.stop()
        return {"cmd_id": cmd_id, "status": "completed"}

    @router.post("/arm/move")
    async def arm_move(req: ArmMoveRequest, x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
        if err:
            return err
        err = _check_franka(franka_backend, cmd_id)
        if err:
            return err

        feedback_fn({"type": "cmd_ack", "cmd_id": cmd_id, "status": "accepted"})

        if req.mode == "joint_position":
            if len(req.values) != 7:
                return _reject(cmd_id, "invalid_input", "joint_position requires 7 values")
            ok = franka_backend.send_joint_position(req.values)
        elif req.mode == "cartesian_pose":
            check = safety.check_arm_cartesian(req.values)
            if not check.ok:
                return _reject(cmd_id, check.reason, check.detail)
            ok = franka_backend.send_cartesian_pose(req.values)
        elif req.mode == "joint_velocity":
            check = safety.check_arm_joint_velocity(req.values)
            if not check.ok:
                return _reject(cmd_id, check.reason, check.detail)
            ok = franka_backend.send_joint_velocity(req.values)
        elif req.mode == "cartesian_velocity":
            if len(req.values) != 6:
                return _reject(cmd_id, "invalid_input", "cartesian_velocity requires 6 values")
            ok = franka_backend.send_cartesian_velocity(req.values)
        else:
            return _reject(cmd_id, "invalid_mode", f"unknown mode: {req.mode}")

        status = "completed" if ok else "failed"
        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": status})
        return {"cmd_id": cmd_id, "status": status}

    @router.post("/arm/stop")
    async def arm_stop(x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
        if err:
            return err
        err = _check_franka(franka_backend, cmd_id)
        if err:
            return err
        franka_backend.emergency_stop()
        return {"cmd_id": cmd_id, "status": "completed"}

    @router.post("/gripper")
    async def gripper(req: GripperRequest, x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
        if err:
            return err
        err = _check_gripper(gripper_backend, cmd_id)
        if err:
            return err

        ok = False
        obj_detected = False

        if req.action == "activate":
            ok = gripper_backend.activate()
        elif req.action == "move":
            # Support both raw position (0-255) and calibrated width (meters)
            if req.position is not None:
                # Raw mode: position is 0-255
                pos = max(0, min(255, req.position))
                check = safety.check_gripper_force(req.force)
                if not check.ok:
                    return _reject(cmd_id, check.reason, check.detail)
                _, obj_detected = gripper_backend.move(pos, req.speed, req.force)
                ok = True
            elif req.width is not None:
                # Calibrated mode: convert width (meters) to position
                # Assumes calibration: 0=open (85mm), 255=closed (0mm)
                # width in meters -> position in 0-255
                width_mm = req.width * 1000  # meters to mm
                # Linear mapping: 85mm -> 0, 0mm -> 255
                pos = int((85.0 - width_mm) / 85.0 * 255)
                pos = max(0, min(255, pos))
                check = safety.check_gripper_force(req.force)
                if not check.ok:
                    return _reject(cmd_id, check.reason, check.detail)
                _, obj_detected = gripper_backend.move(pos, req.speed, req.force)
                ok = True
            else:
                return _reject(cmd_id, "invalid_input", "move requires position or width")
        elif req.action == "grasp":
            check = safety.check_gripper_force(req.force)
            if not check.ok:
                return _reject(cmd_id, check.reason, check.detail)
            obj_detected = gripper_backend.grasp(req.speed, req.force)
            ok = True
        elif req.action == "open":
            _, obj_detected = gripper_backend.open(req.speed, req.force)
            ok = True
        elif req.action == "close":
            _, obj_detected = gripper_backend.close(req.speed, req.force)
            ok = True
        elif req.action == "stop":
            ok = gripper_backend.stop()
        elif req.action == "calibrate":
            ok = gripper_backend.calibrate()
        else:
            return _reject(cmd_id, "invalid_action", f"unknown action: {req.action}")

        status = "completed" if ok else "failed"
        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": status, "object_detected": obj_detected})
        return {"cmd_id": cmd_id, "status": status, "object_detected": obj_detected}

    @router.post("/reset")
    async def reset(req: ResetRequest = ResetRequest(), x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
        if err:
            return err

        n = len(system_logger)

        if n == 0 or req.fraction <= 0:
            base_backend.reset()
            franka_backend.set_control_mode(0)
            return {"cmd_id": cmd_id, "status": "completed", "reversed": 0}

        fraction = max(0.0, min(1.0, req.fraction))
        steps = round(fraction * n)
        if steps == 0:
            return {"cmd_id": cmd_id, "status": "completed", "reversed": 0}

        # Get waypoints to reverse
        waypoints = system_logger.get_waypoints()
        to_reverse = list(reversed(waypoints[n - steps :]))

        loop = asyncio.get_event_loop()
        reversed_count = 0
        for wp in to_reverse:
            try:
                await asyncio.gather(
                    loop.run_in_executor(None, base_backend.execute_action, wp.x, wp.y, wp.theta),
                    loop.run_in_executor(None, franka_backend.send_joint_position, wp.arm_q) if wp.arm_q else asyncio.sleep(0),
                )
                reversed_count += 1
            except Exception:
                logger.exception("Error during trajectory reversal at step %d", reversed_count)
                break

        system_logger.truncate(n - reversed_count)

        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": "completed"})
        return {"cmd_id": cmd_id, "status": "completed", "reversed": reversed_count}

    return router
