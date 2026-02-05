"""GET /state, /health, /state/cameras, /cameras endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, Query
from fastapi.responses import JSONResponse
from typing import Optional

router = APIRouter()


def create_router(state_agg, camera_backend, lease_mgr, base_backend, franka_backend, gripper_backend, system_logger):
    @router.get("/state")
    async def get_state():
        return state_agg.state

    @router.get("/state/cameras")
    async def get_camera_frame(device: Optional[str] = None):
        """Get latest camera frame as JPEG.
        
        Args:
            device: Optional device ID to get frame from
        """
        frame = camera_backend.get_frame(device)
        if frame is None:
            return JSONResponse({"error": "no camera frame available"}, status_code=503)
        return Response(content=frame, media_type="image/jpeg")

    @router.get("/cameras")
    async def list_cameras():
        """List connected cameras."""
        cameras = camera_backend.get_cameras()
        state = camera_backend.get_state()
        return {
            "cameras": cameras,
            "connected": camera_backend.is_connected,
            "streaming": state.get("is_streaming", False) if state else False,
        }

    @router.get("/cameras/{device_id}/frame")
    async def get_device_frame(device_id: str, stream: str = "color"):
        """Get frame from specific camera device.
        
        Args:
            device_id: Camera device identifier
            stream: Stream type (color, depth)
        """
        if stream == "color":
            frame = camera_backend.get_frame(device_id)
            if frame is None:
                return JSONResponse({"error": "no frame available"}, status_code=503)
            return Response(content=frame, media_type="image/jpeg")
        else:
            # For depth, get raw decoded frame
            decoded = camera_backend.get_latest_decoded_frame(stream, device_id)
            if decoded is None:
                return JSONResponse({"error": f"no {stream} frame available"}, status_code=503)
            
            # Return as JSON with metadata
            import cv2
            _, png = cv2.imencode(".png", decoded.frame)
            return Response(content=png.tobytes(), media_type="image/png")

    @router.get("/trajectory")
    async def get_trajectory():
        waypoints = [wp.to_dict() for wp in system_logger.get_waypoints()]
        return {"waypoints": waypoints, "count": len(system_logger)}

    @router.get("/health")
    async def health():
        return {
            "status": "ok",
            "lease": lease_mgr.status(),
            "backends": {
                "base": base_backend.is_connected,
                "franka": franka_backend.is_connected,
                "gripper": gripper_backend.is_connected,
                "cameras": camera_backend.is_connected,
            },
        }

    return router
