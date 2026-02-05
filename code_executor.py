"""Code execution service for running submitted code in isolated subprocess."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Status of code execution."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    STOPPED = "stopped"


@dataclass
class ExecutionResult:
    """Result of code execution."""
    status: ExecutionStatus
    execution_id: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration: float
    error: str = ""


class CodeExecutor:
    """Manages subprocess execution of submitted code.

    Runs code in an isolated subprocess with access to robot_sdk.
    Enforces timeout from lease system.
    """

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._execution_id: Optional[str] = None
        self._start_time: Optional[float] = None
        self._last_result: Optional[ExecutionResult] = None
        self._temp_files: list[Path] = []

    @property
    def is_running(self) -> bool:
        """Check if code is currently executing."""
        return self._process is not None and self._process.poll() is None

    @property
    def status(self) -> ExecutionStatus:
        """Get current execution status."""
        if self._process is None:
            return ExecutionStatus.IDLE
        if self._process.poll() is None:
            return ExecutionStatus.RUNNING
        if self._last_result:
            return self._last_result.status
        return ExecutionStatus.IDLE

    async def execute(
        self,
        code: str,
        execution_id: str,
        timeout: float = 300.0,
    ) -> ExecutionResult:
        """Execute code in subprocess.

        Args:
            code: Python code to execute
            execution_id: Unique ID for this execution
            timeout: Maximum execution time in seconds

        Returns:
            ExecutionResult with status, stdout, stderr, etc.

        Raises:
            RuntimeError: If code is already running
        """
        if self.is_running:
            raise RuntimeError("Code is already running. Stop it first.")

        self._execution_id = execution_id
        self._start_time = time.time()

        # Create temporary Python file with submitted code
        temp_file = self._create_temp_file(code)
        self._temp_files.append(temp_file)

        logger.info(f"Executing code (ID: {execution_id}): {temp_file}")

        try:
            # Start subprocess
            self._process = subprocess.Popen(
                ["python3", str(temp_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(__file__),  # Set working directory to agent server root
                env=self._get_env(),
            )

            # Wait for completion or timeout
            try:
                stdout, stderr = self._process.communicate(timeout=timeout)
                exit_code = self._process.returncode
                duration = time.time() - self._start_time

                if exit_code == 0:
                    status = ExecutionStatus.COMPLETED
                    error = ""
                else:
                    status = ExecutionStatus.FAILED
                    error = f"Process exited with code {exit_code}"

                result = ExecutionResult(
                    status=status,
                    execution_id=execution_id,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration=duration,
                    error=error,
                )

            except subprocess.TimeoutExpired:
                # Kill process on timeout
                self._process.kill()
                stdout, stderr = self._process.communicate()
                duration = time.time() - self._start_time

                result = ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    execution_id=execution_id,
                    exit_code=None,
                    stdout=stdout,
                    stderr=stderr,
                    duration=duration,
                    error=f"Execution timed out after {timeout}s",
                )

        except Exception as e:
            duration = time.time() - self._start_time if self._start_time else 0

            result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                execution_id=execution_id,
                exit_code=None,
                stdout="",
                stderr=str(e),
                duration=duration,
                error=f"Failed to execute code: {e}",
            )

        finally:
            self._process = None
            self._last_result = result

        logger.info(
            f"Execution {execution_id} finished: {result.status} "
            f"(duration: {result.duration:.2f}s, exit_code: {result.exit_code})"
        )

        return result

    def stop(self) -> bool:
        """Stop currently running code.

        Sends SIGTERM for graceful shutdown, then SIGKILL if needed.

        Returns:
            True if code was stopped, False if nothing was running
        """
        if not self.is_running:
            return False

        logger.info(f"Stopping execution {self._execution_id}")

        # Try graceful shutdown first
        self._process.terminate()

        try:
            # Wait up to 2 seconds for graceful shutdown
            self._process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            # Force kill if still running
            logger.warning(f"Graceful shutdown failed, force killing {self._execution_id}")
            self._process.kill()
            self._process.wait()

        duration = time.time() - self._start_time if self._start_time else 0

        # Capture any output
        try:
            stdout, stderr = self._process.communicate(timeout=0.5)
        except:
            stdout, stderr = "", ""

        self._last_result = ExecutionResult(
            status=ExecutionStatus.STOPPED,
            execution_id=self._execution_id or "unknown",
            exit_code=self._process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration=duration,
            error="Execution stopped by user",
        )

        self._process = None
        return True

    def get_last_result(self) -> Optional[ExecutionResult]:
        """Get result from last execution."""
        return self._last_result

    def cleanup_temp_files(self) -> None:
        """Remove temporary code files."""
        for temp_file in self._temp_files:
            try:
                temp_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file}: {e}")
        self._temp_files.clear()

    def _create_temp_file(self, code: str) -> Path:
        """Create temporary Python file with code + SDK initialization.

        Args:
            code: User-submitted Python code

        Returns:
            Path to temporary file
        """
        # Wrapper code that initializes robot_sdk before running user code
        wrapper = f'''#!/usr/bin/env python3
"""Auto-generated code execution wrapper."""

import sys
import os

# Add parent directory to path so robot_sdk can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize robot_sdk with backend connections
from backends.franka import FrankaBackend
from backends.base import BaseBackend
from backends.gripper import GripperBackend
from config import FrankaBackendConfig, BaseBackendConfig, GripperBackendConfig
from robot_sdk import ArmAPI, BaseAPI, GripperAPI, SensorAPI
import robot_sdk

# Create backend configurations (use environment variables or defaults)
import asyncio

dry_run = os.getenv("ROBOT_DRY_RUN", "false").lower() == "true"

franka_config = FrankaBackendConfig(
    host=os.getenv("FRANKA_IP", "localhost"),
    cmd_port=5555,
    state_port=5556,
    stream_port=5557,
)

base_config = BaseBackendConfig(
    host=os.getenv("BASE_IP", "localhost"),
    port=50000,
    authkey=b"tidybot",
)

gripper_config = GripperBackendConfig(
    host=os.getenv("GRIPPER_IP", "localhost"),
    cmd_port=5570,
    state_port=5571,
)

# Create backends
franka_backend = FrankaBackend(franka_config, dry_run=dry_run)
base_backend = BaseBackend(base_config, dry_run=dry_run)
gripper_backend = GripperBackend(gripper_config, dry_run=dry_run)

# Connect to backends (gracefully handle unavailable ones)
async def init_backends():
    # Franka (arm) - required
    try:
        await franka_backend.connect()
        print("[SDK] Franka backend connected")
    except Exception as e:
        print(f"[SDK] WARNING: Franka backend unavailable: {{e}}")

    # Base - optional
    try:
        await base_backend.connect()
        print("[SDK] Base backend connected")
    except Exception as e:
        print(f"[SDK] WARNING: Base backend unavailable: {{e}}")

    # Gripper - optional
    try:
        await gripper_backend.connect()
        print("[SDK] Gripper backend connected")
    except Exception as e:
        print(f"[SDK] WARNING: Gripper backend unavailable: {{e}}")

asyncio.run(init_backends())

# Initialize SDK global instances
robot_sdk.arm = ArmAPI(franka_backend)
robot_sdk.base = BaseAPI(base_backend)
robot_sdk.gripper = GripperAPI(gripper_backend)
robot_sdk.sensors = SensorAPI(franka_backend, base_backend, gripper_backend)

# Make them available for import
arm = robot_sdk.arm
base = robot_sdk.base
gripper = robot_sdk.gripper
sensors = robot_sdk.sensors

# Also expose backends directly for advanced usage
# (same pattern as rewind orchestrator uses)

# ============================================================================
# USER CODE STARTS HERE
# ============================================================================

{code}

# ============================================================================
# USER CODE ENDS HERE
# ============================================================================

# Cleanup (disconnect backends)
async def cleanup():
    await franka_backend.disconnect()
    await base_backend.disconnect()
    await gripper_backend.disconnect()

asyncio.run(cleanup())
'''

        # Create temporary file
        fd, path = tempfile.mkstemp(suffix=".py", prefix="robot_code_")
        os.write(fd, wrapper.encode("utf-8"))
        os.close(fd)

        return Path(path)

    def _get_env(self) -> dict:
        """Get environment variables for subprocess.

        Returns current environment with Python path modifications.
        """
        env = os.environ.copy()

        # Add agent server directory to Python path (for backends, robot_sdk, etc.)
        agent_server_dir = os.path.dirname(__file__)
        agent_server_dir = os.path.abspath(agent_server_dir)

        # Add franka_server to Python path (needed for FrankaClient import)
        franka_pkg = os.path.join(
            agent_server_dir,
            "..",
            "franka_interact",
            "franka_server",
        )
        franka_pkg = os.path.abspath(franka_pkg)

        # Add gripper_server to Python path
        gripper_pkg = os.path.join(
            agent_server_dir,
            "..",
            "gripper_server",
        )
        gripper_pkg = os.path.abspath(gripper_pkg)

        # Add all paths to PYTHONPATH
        python_path = env.get("PYTHONPATH", "")
        paths = [agent_server_dir, franka_pkg, gripper_pkg]
        if python_path:
            paths.append(python_path)
        env["PYTHONPATH"] = ":".join(paths)

        return env
