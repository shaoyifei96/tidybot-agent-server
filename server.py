"""Hardware server — FastAPI app wiring everything together."""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Add system_logger to path (sibling package)
_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SERVER_DIR)
_SYSTEM_LOGGER_DIR = os.path.join(_PROJECT_ROOT, "system_logger")
if _SYSTEM_LOGGER_DIR not in sys.path:
    sys.path.insert(0, _SYSTEM_LOGGER_DIR)

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from backends.base import BaseBackend
from backends.cameras import CameraBackend
from backends.franka import FrankaBackend
from backends.gripper import GripperBackend
from config import LeaseConfig, ServerConfig, ServiceManagerConfig, default_services
from lease import LeaseManager
from routes.ws import FeedbackBroadcaster
from safety import SafetyEnvelope
from services import ServiceManager
from state import StateAggregator

# Use system_logger for unified state recording and coordinated rewind
from system_logger import SystemLogger, RewindOrchestrator, LoggerConfig, RewindConfig
from system_logger.config import WorkspaceBounds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_app(cfg: ServerConfig, service_mgr: ServiceManager | None = None) -> FastAPI:
    app = FastAPI(title="TidyBot Hardware Server")

    # Initialize app state for background tasks
    app.state.background_tasks = set()

    @app.get("/")
    async def root():
        return RedirectResponse(url="/services/dashboard")

    # -- backends ------------------------------------------------------------
    base_backend = BaseBackend(cfg.base, dry_run=cfg.dry_run)
    franka_backend = FrankaBackend(cfg.franka, dry_run=cfg.dry_run)
    gripper_backend = GripperBackend(cfg.gripper, dry_run=cfg.dry_run)
    camera_backend = CameraBackend(cfg.cameras, dry_run=cfg.dry_run)

    # -- core services -------------------------------------------------------
    state_agg = StateAggregator(cfg, base_backend, franka_backend, gripper_backend)
    safety = SafetyEnvelope(cfg.safety)
    feedback = FeedbackBroadcaster()

    # Unified state logger (replaces TrajectoryRecorder)
    logger_config = LoggerConfig(
        max_waypoints=cfg.max_trajectory_length,
        record_interval=cfg.trajectory_interval,
        base_position_threshold=cfg.trajectory_position_threshold,
        base_orientation_threshold=cfg.trajectory_orientation_threshold,
    )
    system_logger = SystemLogger(logger_config)

    # Workspace bounds from safety config
    workspace_bounds = WorkspaceBounds(
        base_x_min=cfg.safety.base_workspace_min[0],
        base_x_max=cfg.safety.base_workspace_max[0],
        base_y_min=cfg.safety.base_workspace_min[1],
        base_y_max=cfg.safety.base_workspace_max[1],
    )

    # Rewind orchestrator (replaces RewindManager + SafetyMonitor)
    rewind_config = RewindConfig(
        rewind_base=True,
        rewind_arm=True,  # Enable coordinated arm+base rewind
        rewind_gripper=False,
    )
    rewind_orchestrator = RewindOrchestrator(system_logger, rewind_config, workspace_bounds)
    rewind_orchestrator.set_backends(
        base_backend=base_backend,
        arm_backend=franka_backend,
        gripper_backend=gripper_backend,
    )

    lease_mgr = LeaseManager(
        cfg.lease,
        motors_moving_fn=state_agg.motors_moving,
        on_lease_event=feedback.broadcast,
    )

    # Wire lease-end callback: rewind to home + clear trajectory
    if cfg.lease.reset_on_release:
        async def _on_lease_end():
            result = await rewind_orchestrator.reset_to_home()
            if result.success or result.steps_rewound == 0:
                system_logger.clear()
            else:
                logger.error("Lease-end reset failed: %s", result.error)

        lease_mgr.set_on_lease_end(_on_lease_end)

    # -- routes --------------------------------------------------------------
    from routes.commands import create_router as cmd_router
    from routes.lease_routes import create_router as lease_router
    from routes.rewind_routes import create_router as rewind_router
    from routes.state_routes import create_router as state_router
    from routes.ws import create_router as ws_router
    from routes.code_routes import init_code_routes
    from routes.sdk_docs import router as sdk_docs_router

    app.include_router(state_router(state_agg, camera_backend, lease_mgr, base_backend, franka_backend, gripper_backend, system_logger))
    app.include_router(lease_router(lease_mgr))
    app.include_router(cmd_router(lease_mgr, safety, base_backend, franka_backend, gripper_backend, feedback.broadcast, state_agg, system_logger))
    app.include_router(rewind_router(rewind_orchestrator, lease_mgr, system_logger))
    app.include_router(ws_router(state_agg, feedback, cfg, camera_backend))
    app.include_router(init_code_routes(lease_mgr))
    app.include_router(sdk_docs_router)

    # Service manager routes
    from routes.service_routes import create_router as service_router
    app.include_router(service_router(service_mgr))  # Pass None if disabled
    if service_mgr is not None:
        # Wire up event broadcasting for service events
        service_mgr._on_event = feedback.broadcast

    # -- lifecycle -----------------------------------------------------------
    @app.on_event("startup")
    async def startup():
        logger.info("Starting hardware server (dry_run=%s)", cfg.dry_run)

        # Start service manager first if enabled
        if service_mgr is not None:
            await service_mgr.start()

        # Connect to backends - failures are logged but don't crash the server
        try:
            await base_backend.connect()
        except Exception as e:
            logger.error("Failed to connect to base backend: %s", e)

        try:
            await franka_backend.connect()
        except Exception as e:
            logger.error("Failed to connect to franka backend: %s", e)

        try:
            await gripper_backend.connect()
        except Exception as e:
            logger.error("Failed to connect to gripper backend: %s", e)

        try:
            await camera_backend.start()
        except Exception as e:
            logger.error("Failed to start camera backend: %s", e)

        await state_agg.start()
        await lease_mgr.start()

        # Start unified state recording
        await system_logger.start(state_fn=lambda: state_agg.state)

        logger.info("Hardware server ready on %s:%d", cfg.host, cfg.port)

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("Shutting down hardware server")

        # Stop any running code execution
        try:
            from routes.code_routes import get_executor
            executor = get_executor()
            if executor.is_running:
                logger.info("Stopping running code execution")
                executor.stop()
            executor.cleanup_temp_files()
        except Exception as e:
            logger.warning(f"Failed to cleanup code executor: {e}")

        # Stop state recording
        await system_logger.stop()

        await lease_mgr.stop()
        await state_agg.stop()
        await camera_backend.stop()
        await gripper_backend.disconnect()
        await franka_backend.disconnect()
        await base_backend.disconnect()

        # Stop service manager last
        if service_mgr is not None:
            await service_mgr.stop()

    return app


def main():
    parser = argparse.ArgumentParser(description="TidyBot Hardware Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--dry-run", action="store_true", help="Use simulated backends")
    parser.add_argument(
        "--auto-start-services",
        action="store_true",
        help="Auto-start backend services (base, franka, controller) on startup",
    )
    parser.add_argument(
        "--no-service-manager",
        action="store_true",
        help="Disable service management entirely",
    )
    parser.add_argument(
        "--no-reset-on-release",
        action="store_true",
        help="Disable auto-rewind to home when lease ends",
    )
    args = parser.parse_args()

    # Build server config
    svc_mgr_cfg = ServiceManagerConfig(
        enabled=not args.no_service_manager,
        auto_start=args.auto_start_services,
    )
    lease_cfg = LeaseConfig()
    if args.no_reset_on_release:
        lease_cfg.reset_on_release = False

    cfg = ServerConfig(
        host=args.host,
        port=args.port,
        dry_run=args.dry_run,
        service_manager=svc_mgr_cfg,
        lease=lease_cfg,
    )

    # Create service manager if enabled
    service_mgr = None
    if cfg.service_manager.enabled:
        # Create FeedbackBroadcaster for service events
        # Note: We create a temporary one here; events will also be broadcast
        # via the main feedback broadcaster once the app is built
        service_mgr = ServiceManager(
            config=cfg.service_manager,
            services=default_services(),
            dry_run=cfg.dry_run,
        )

    app = build_app(cfg, service_mgr=service_mgr)
    uvicorn.run(app, host=cfg.host, port=cfg.port, access_log=False)


if __name__ == "__main__":
    main()
