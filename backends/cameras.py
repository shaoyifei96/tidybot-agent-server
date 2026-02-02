"""Camera capture background threads."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from config import CameraConfig

logger = logging.getLogger(__name__)


class CameraBackend:
    """Captures frames from V4L2/RTSP cameras in background threads."""

    def __init__(self, config: CameraConfig, dry_run: bool = False) -> None:
        self._cfg = config
        self._dry_run = dry_run
        self._threads: list[threading.Thread] = []
        self._running = False
        # device -> latest JPEG bytes
        self._frames: dict[str, bytes] = {}
        self._lock = threading.Lock()

    async def start(self) -> None:
        if not self._cfg.enabled or self._dry_run:
            logger.info("CameraBackend: disabled or dry-run")
            return
        self._running = True
        for dev in self._cfg.devices:
            t = threading.Thread(target=self._capture_loop, args=(dev,), daemon=True)
            t.start()
            self._threads.append(t)
        logger.info("CameraBackend: started %d capture threads", len(self._threads))

    async def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()

    def get_frame(self, device: Optional[str] = None) -> Optional[bytes]:
        with self._lock:
            if device:
                return self._frames.get(device)
            # Return first available
            for v in self._frames.values():
                return v
            return None

    def get_all_frames(self) -> dict[str, bytes]:
        with self._lock:
            return dict(self._frames)

    def _capture_loop(self, device: str) -> None:
        try:
            import cv2
        except ImportError:
            logger.error("opencv-python not installed, camera capture disabled")
            return

        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            logger.error("Failed to open camera %s", device)
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self._cfg.fps)

        period = 1.0 / self._cfg.fps
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            _, jpeg = cv2.imencode(".jpg", frame)
            with self._lock:
                self._frames[device] = jpeg.tobytes()
            time.sleep(period)

        cap.release()
