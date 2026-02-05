"""Camera backend - WebSocket client to camera_server."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from typing import Optional, Dict, List, Any

# Add camera_server to path
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'camera_server'))

try:
    from camera_server.client import CameraClient, DecodedFrame
    from camera_server.protocol import CameraStateMsg, CameraInfo
    CAMERA_CLIENT_AVAILABLE = True
except ImportError:
    CAMERA_CLIENT_AVAILABLE = False
    CameraClient = None
    DecodedFrame = None
    CameraStateMsg = None
    CameraInfo = None

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from config import CameraBackendConfig

logger = logging.getLogger(__name__)


class CameraBackendError(Exception):
    """Raised when camera backend is unavailable or connection fails."""
    pass


class CameraBackend:
    """WebSocket client wrapper for camera_server.
    
    Connects to the camera_server and provides frame access.
    Follows the same pattern as BaseBackend/FrankaBackend.
    """

    def __init__(self, config: CameraBackendConfig, dry_run: bool = False) -> None:
        self._cfg = config
        self._dry_run = dry_run
        self._client: Optional[CameraClient] = None
        self._connected = False
        self._streaming = False
        
        # Frame cache for HTTP endpoint
        self._frame_cache: Dict[str, bytes] = {}  # device_id -> JPEG bytes
        self._frame_lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Connect to camera server and start streaming."""
        if self._dry_run:
            logger.info("CameraBackend: dry-run mode, skipping connection")
            return
        
        if not self._cfg.enabled:
            logger.info("CameraBackend: disabled in config")
            return
        
        if not CAMERA_CLIENT_AVAILABLE:
            logger.error("CameraBackend: camera_server client not available")
            return
        
        try:
            self._client = CameraClient(
                server_ip=self._cfg.host,
                port=self._cfg.port,
                timeout=self._cfg.timeout,
            )
            
            if not self._client.connect():
                logger.error("CameraBackend: failed to connect to camera server")
                self._client = None
                return
            
            self._connected = True
            logger.info("CameraBackend: connected to %s:%d", self._cfg.host, self._cfg.port)
            
            # Set up frame callback for caching
            self._client.set_frame_callback(self._on_frame)
            
            # Subscribe to streams
            if self._cfg.auto_subscribe:
                self._client.subscribe(
                    streams=self._cfg.streams,
                    device_id="all",
                    fps=self._cfg.stream_fps,
                    quality=self._cfg.quality,
                )
                self._streaming = True
                logger.info("CameraBackend: subscribed to %s at %d fps", 
                           self._cfg.streams, self._cfg.stream_fps)
            
        except Exception as e:
            logger.error("CameraBackend: connection failed: %s", e)
            self._client = None
            self._connected = False

    async def stop(self) -> None:
        """Disconnect from camera server."""
        if self._client:
            try:
                self._client.disconnect()
            except Exception as e:
                logger.error("CameraBackend: error disconnecting: %s", e)
            self._client = None
        self._connected = False
        self._streaming = False
        logger.info("CameraBackend: disconnected")

    @property
    def is_connected(self) -> bool:
        """Return True if connected to camera server."""
        return self._dry_run or self._connected

    # -- frame callback ------------------------------------------------------

    def _on_frame(self, frame: DecodedFrame) -> None:
        """Callback for received frames - cache as JPEG."""
        if not CV2_AVAILABLE:
            return
        
        try:
            if frame.stream_type == "color":
                # Encode as JPEG for HTTP endpoint
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, self._cfg.quality]
                _, jpeg = cv2.imencode(".jpg", frame.frame, encode_params)
                with self._frame_lock:
                    self._frame_cache[frame.device_id] = jpeg.tobytes()
        except Exception as e:
            logger.error("CameraBackend: error encoding frame: %s", e)

    # -- queries -------------------------------------------------------------

    def get_frame(self, device: Optional[str] = None) -> Optional[bytes]:
        """Get latest frame as JPEG bytes.
        
        Args:
            device: Device ID, or None for first available
            
        Returns:
            JPEG bytes or None
        """
        if self._dry_run:
            return None
        
        # Try cached frame first (from streaming)
        with self._frame_lock:
            if device:
                if device in self._frame_cache:
                    return self._frame_cache[device]
            else:
                for v in self._frame_cache.values():
                    return v
        
        # No cached frame, try to get one directly
        if self._client and self._connected:
            try:
                frame = self._client.get_frame("color", device or "any", self._cfg.quality)
                if frame and CV2_AVAILABLE:
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, self._cfg.quality]
                    _, jpeg = cv2.imencode(".jpg", frame.frame, encode_params)
                    return jpeg.tobytes()
            except Exception as e:
                logger.error("CameraBackend: error getting frame: %s", e)
        
        return None

    def get_all_frames(self) -> Dict[str, bytes]:
        """Get all cached frames.
        
        Returns:
            Dict of device_id -> JPEG bytes
        """
        with self._frame_lock:
            return dict(self._frame_cache)

    def get_state(self) -> Optional[Dict[str, Any]]:
        """Get camera state.
        
        Returns:
            Dict with cameras info or None
        """
        if self._dry_run:
            return {"cameras": [], "is_streaming": False}
        
        if not self._client or not self._connected:
            return None
        
        try:
            state = self._client.get_state()
            if state:
                return state.to_dict()
            return None
        except Exception as e:
            logger.error("CameraBackend: error getting state: %s", e)
            return None

    def get_cameras(self) -> List[Dict[str, Any]]:
        """Get list of connected cameras.
        
        Returns:
            List of camera info dicts
        """
        if self._dry_run:
            return []
        
        if self._client and self._client.latest_state:
            return [c.to_dict() for c in self._client.latest_state.cameras]
        return []

    def get_latest_decoded_frame(
        self, 
        stream_type: str = "color",
        device_id: Optional[str] = None
    ) -> Optional[DecodedFrame]:
        """Get latest decoded frame (numpy array).
        
        For WebSocket forwarding where we need raw frames.
        
        Args:
            stream_type: Stream type
            device_id: Device ID or None for first available
            
        Returns:
            DecodedFrame or None
        """
        if self._dry_run or not self._client:
            return None
        
        return self._client.get_latest_frame(stream_type, device_id)

    # -- commands ------------------------------------------------------------

    def subscribe(
        self,
        streams: Optional[List[str]] = None,
        device_id: str = "all",
        fps: Optional[int] = None,
        quality: Optional[int] = None,
    ) -> bool:
        """Subscribe to camera streams.
        
        Args:
            streams: Stream types (default: from config)
            device_id: Device ID or "all"
            fps: Streaming FPS (default: from config)
            quality: JPEG quality (default: from config)
            
        Returns:
            bool: True if successful
        """
        if self._dry_run or not self._client:
            return False
        
        try:
            result = self._client.subscribe(
                streams=streams or self._cfg.streams,
                device_id=device_id,
                fps=fps or self._cfg.stream_fps,
                quality=quality or self._cfg.quality,
            )
            if result:
                self._streaming = True
            return result
        except Exception as e:
            logger.error("CameraBackend: subscribe error: %s", e)
            return False

    def unsubscribe(
        self,
        streams: Optional[List[str]] = None,
        device_id: str = "all",
    ) -> bool:
        """Unsubscribe from camera streams.
        
        Args:
            streams: Stream types (None = all)
            device_id: Device ID or "all"
            
        Returns:
            bool: True if successful
        """
        if self._dry_run or not self._client:
            return False
        
        try:
            result = self._client.unsubscribe(streams, device_id)
            if not streams:
                self._streaming = False
            return result
        except Exception as e:
            logger.error("CameraBackend: unsubscribe error: %s", e)
            return False
