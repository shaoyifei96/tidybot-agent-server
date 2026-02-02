"""POST /cmd/* endpoints — command dispatch with lease + safety checks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/cmd")


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
    action: str  # move, grasp, open, close, stop, homing
    width: Optional[float] = None
    speed: float = 0.1
    force: float = 20.0


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


# -- router factory ----------------------------------------------------------

logger = logging.getLogger(__name__)


def create_router(lease_mgr, safety, base_backend, franka_backend, feedback_fn, state_agg, trajectory):
    """feedback_fn(event_dict) broadcasts to operator's /ws/feedback."""

    @router.post("/base/move")
    async def base_move(req: BaseMoveRequest, x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
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
            trajectory.record(state_agg.state)

        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": "completed"})
        return {"cmd_id": cmd_id, "status": "completed"}

    @router.post("/base/stop")
    async def base_stop(x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
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
        if ok and req.mode in ("joint_position", "cartesian_pose"):
            trajectory.record(state_agg.state)
        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": status})
        return {"cmd_id": cmd_id, "status": status}

    @router.post("/arm/stop")
    async def arm_stop(x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
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

        if req.action == "move":
            ok = franka_backend.gripper_move(req.width or 0.04, req.speed)
        elif req.action == "grasp":
            check = safety.check_gripper_force(req.force)
            if not check.ok:
                return _reject(cmd_id, check.reason, check.detail)
            ok = franka_backend.gripper_grasp(req.width or 0.04, req.speed, req.force)
        elif req.action == "open":
            ok = franka_backend.gripper_open(req.speed)
        elif req.action == "close":
            ok = franka_backend.gripper_close(req.speed)
        elif req.action == "stop":
            ok = franka_backend.gripper_stop()
        elif req.action == "homing":
            ok = franka_backend.gripper_homing()
        else:
            return _reject(cmd_id, "invalid_action", f"unknown action: {req.action}")

        status = "completed" if ok else "failed"
        if ok and req.action in ("move", "grasp", "open", "close"):
            trajectory.record(state_agg.state)
        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": status})
        return {"cmd_id": cmd_id, "status": status}

    @router.post("/reset")
    async def reset(req: ResetRequest = ResetRequest(), x_lease_id: Optional[str] = Header(None)):
        cmd_id = str(uuid.uuid4())[:8]
        err = _check_lease(lease_mgr, x_lease_id, cmd_id)
        if err:
            return err

        history = trajectory.get_history()
        n = len(history)

        if n == 0 or req.fraction <= 0:
            # Nothing to reverse — just idle the robot
            base_backend.reset()
            franka_backend.set_control_mode(0)
            return {"cmd_id": cmd_id, "status": "completed", "reversed": 0}

        fraction = max(0.0, min(1.0, req.fraction))
        steps = round(fraction * n)
        if steps == 0:
            return {"cmd_id": cmd_id, "status": "completed", "reversed": 0}

        # Take the last `steps` waypoints in reverse order
        to_reverse = list(reversed(history[n - steps :]))

        loop = asyncio.get_event_loop()
        reversed_count = 0
        for wp in to_reverse:
            try:
                base_pose = wp["base_pose"]
                arm_q = wp["arm_q"]
                await asyncio.gather(
                    loop.run_in_executor(None, base_backend.execute_action, base_pose[0], base_pose[1], base_pose[2]),
                    loop.run_in_executor(None, franka_backend.send_joint_position, arm_q),
                )
                reversed_count += 1
            except Exception:
                logger.exception("Error during trajectory reversal at step %d", reversed_count)
                break

        # Truncate the reversed portion from history
        trajectory.truncate(n - reversed_count)

        feedback_fn({"type": "cmd_result", "cmd_id": cmd_id, "status": "completed"})
        return {"cmd_id": cmd_id, "status": "completed", "reversed": reversed_count}

    return router
