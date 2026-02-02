"""Hardware server — FastAPI app wiring everything together."""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn
from fastapi import FastAPI

from backends.base import BaseBackend
from backends.cameras import CameraBackend
from backends.franka import FrankaBackend
from config import ServerConfig
from lease import LeaseManager
from routes.ws import FeedbackBroadcaster
from safety import SafetyEnvelope
from state import StateAggregator
from trajectory import TrajectoryRecorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_app(cfg: ServerConfig) -> FastAPI:
    app = FastAPI(title="TidyBot Hardware Server")

    # -- backends ------------------------------------------------------------
    base_backend = BaseBackend(cfg.base, dry_run=cfg.dry_run)
    franka_backend = FrankaBackend(cfg.franka, dry_run=cfg.dry_run)
    camera_backend = CameraBackend(cfg.cameras, dry_run=cfg.dry_run)

    # -- core services -------------------------------------------------------
    state_agg = StateAggregator(cfg, base_backend, franka_backend)
    safety = SafetyEnvelope(cfg.safety)
    feedback = FeedbackBroadcaster()

    trajectory = TrajectoryRecorder(max_length=cfg.max_trajectory_length)

    lease_mgr = LeaseManager(
        cfg.lease,
        motors_moving_fn=state_agg.motors_moving,
        on_lease_event=feedback.broadcast,
    )

    # -- routes --------------------------------------------------------------
    from routes.commands import create_router as cmd_router
    from routes.lease_routes import create_router as lease_router
    from routes.state_routes import create_router as state_router
    from routes.ws import create_router as ws_router

    app.include_router(state_router(state_agg, camera_backend, lease_mgr, base_backend, franka_backend, trajectory))
    app.include_router(lease_router(lease_mgr))
    app.include_router(cmd_router(lease_mgr, safety, base_backend, franka_backend, feedback.broadcast, state_agg, trajectory))
    app.include_router(ws_router(state_agg, feedback, cfg))

    # -- lifecycle -----------------------------------------------------------
    @app.on_event("startup")
    async def startup():
        logger.info("Starting hardware server (dry_run=%s)", cfg.dry_run)
        await base_backend.connect()
        await franka_backend.connect()
        await camera_backend.start()
        await state_agg.start()
        await lease_mgr.start()
        logger.info("Hardware server ready on %s:%d", cfg.host, cfg.port)

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("Shutting down hardware server")
        await lease_mgr.stop()
        await state_agg.stop()
        await camera_backend.stop()
        await franka_backend.disconnect()
        await base_backend.disconnect()

    return app


def main():
    parser = argparse.ArgumentParser(description="TidyBot Hardware Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--dry-run", action="store_true", help="Use simulated backends")
    args = parser.parse_args()

    cfg = ServerConfig(host=args.host, port=args.port, dry_run=args.dry_run)
    app = build_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
