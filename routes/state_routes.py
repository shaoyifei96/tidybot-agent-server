"""GET /state, /health, /state/cameras endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

router = APIRouter()


def create_router(state_agg, camera_backend, lease_mgr, base_backend, franka_backend, trajectory):
    @router.get("/state")
    async def get_state():
        return state_agg.state

    @router.get("/state/cameras")
    async def get_cameras():
        frame = camera_backend.get_frame()
        if frame is None:
            return JSONResponse({"error": "no camera frame available"}, status_code=503)
        return Response(content=frame, media_type="image/jpeg")

    @router.get("/trajectory")
    async def get_trajectory():
        return {"waypoints": trajectory.get_history(), "count": len(trajectory)}

    @router.get("/health")
    async def health():
        return {
            "status": "ok",
            "lease": lease_mgr.status(),
            "backends": {
                "base": base_backend._base is not None or base_backend._dry_run,
                "franka": franka_backend._client is not None or franka_backend._dry_run,
                "cameras": camera_backend._cfg.enabled,
            },
        }

    return router
