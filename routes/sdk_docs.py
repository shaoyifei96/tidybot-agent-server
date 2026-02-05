"""Auto-generated SDK documentation endpoint.

Introspects the robot_sdk module at runtime to generate accurate documentation.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/code", tags=["code"])


def get_method_info(method: Any) -> dict:
    """Extract method information including signature and docstring."""
    try:
        sig = inspect.signature(method)
        params = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            param_info = {"name": name}
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = str(param.annotation).replace("typing.", "")
            if param.default != inspect.Parameter.empty:
                param_info["default"] = repr(param.default)
            params.append(param_info)

        return_type = None
        if sig.return_annotation != inspect.Signature.empty:
            return_type = str(sig.return_annotation).replace("typing.", "")

        return {
            "signature": str(sig),
            "params": params,
            "return_type": return_type,
            "docstring": inspect.getdoc(method) or "",
        }
    except Exception as e:
        return {"error": str(e)}


def get_class_info(cls: type) -> dict:
    """Extract class information including all public methods."""
    methods = {}
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        methods[name] = get_method_info(method)

    return {
        "docstring": inspect.getdoc(cls) or "",
        "methods": methods,
    }


def generate_sdk_docs() -> dict:
    """Generate SDK documentation by introspecting robot_sdk module."""
    docs = {
        "version": "1.0.0",
        "description": "Robot SDK for code execution. Import these modules in submitted code.",
        "modules": {},
        "usage": {
            "example": """from robot_sdk import arm, base, gripper, sensors

# Move arm
arm.move_joints([0, -0.785, 0, -2.356, 0, 1.571, 0.785])

# Read sensors
joints = sensors.get_arm_joints()
print(f"Current joints: {joints}")
""",
            "notes": [
                "All methods are synchronous (blocking)",
                "Methods raise exceptions on failure",
                "Robot holds position when code stops (auto-hold)",
                "Unavailable backends print warning but don't crash",
            ],
        },
    }

    try:
        # Import SDK modules
        from robot_sdk.arm import ArmAPI
        from robot_sdk.base import BaseAPI
        from robot_sdk.gripper import GripperAPI
        from robot_sdk.sensors import SensorAPI

        docs["modules"]["arm"] = {
            "import": "from robot_sdk import arm",
            "description": "Arm control - joint and cartesian movements",
            **get_class_info(ArmAPI),
        }

        docs["modules"]["base"] = {
            "import": "from robot_sdk import base",
            "description": "Mobile base control - position and velocity",
            **get_class_info(BaseAPI),
        }

        docs["modules"]["gripper"] = {
            "import": "from robot_sdk import gripper",
            "description": "Gripper control - open, close, grasp",
            **get_class_info(GripperAPI),
        }

        docs["modules"]["sensors"] = {
            "import": "from robot_sdk import sensors",
            "description": "Read-only sensor access - arm, base, gripper state",
            **get_class_info(SensorAPI),
        }

        # Add constants
        docs["constants"] = {
            "arm_control_modes": {
                "IDLE": 0,
                "JOINT_POSITION": 1,
                "JOINT_VELOCITY": 2,
                "TORQUE": 3,
                "CARTESIAN_POSE": 4,
                "CARTESIAN_VELOCITY": 5,
            },
            "gripper_range": {
                "min": 0,
                "max": 255,
                "description": "0 = fully open, 255 = fully closed",
            },
        }

        # Add direct backend access info
        docs["advanced"] = {
            "franka_backend": {
                "description": "Direct access to Franka arm backend (like rewind uses)",
                "available_in_code": True,
                "example": """# Direct backend access
franka_backend.set_control_mode(1)  # JOINT_POSITION
franka_backend.send_joint_position(target_q, blocking=False)
state = franka_backend.get_state()
""",
                "methods": [
                    "set_control_mode(mode: int)",
                    "send_joint_position(q: list, blocking: bool)",
                    "send_cartesian_pose(pose: list)",
                    "send_joint_velocity(dq: list)",
                    "send_cartesian_velocity(velocity: list)",
                    "get_state() -> dict",
                    "emergency_stop()",
                ],
            },
            "base_backend": {
                "description": "Direct access to mobile base backend",
                "available_in_code": True,
                "methods": [
                    "execute_action(x, y, theta)",
                    "set_target_velocity(vx, vy, wz, frame)",
                    "get_state() -> dict",
                    "stop()",
                ],
            },
            "gripper_backend": {
                "description": "Direct access to gripper backend",
                "available_in_code": True,
                "methods": [
                    "activate()",
                    "move(position, speed, force)",
                    "open(speed, force)",
                    "close(speed, force)",
                    "grasp(speed, force)",
                    "stop()",
                    "get_state() -> dict",
                ],
            },
        }

    except ImportError as e:
        docs["error"] = f"Failed to import SDK modules: {e}"

    return docs


@router.get("/sdk")
async def get_sdk_documentation():
    """Get auto-generated SDK documentation.

    Returns documentation for all available SDK modules, methods, and their
    signatures. This is generated by introspecting the actual code, so it's
    always accurate.

    No lease required.
    """
    return generate_sdk_docs()


@router.get("/sdk/markdown")
async def get_sdk_markdown():
    """Get SDK documentation as markdown.

    Useful for displaying in documentation viewers or chat interfaces.

    No lease required.
    """
    docs = generate_sdk_docs()

    md = f"# Robot SDK Documentation\n\n"
    md += f"**Version:** {docs['version']}\n\n"
    md += f"{docs['description']}\n\n"

    # Usage
    md += "## Quick Start\n\n"
    md += "```python\n"
    md += docs["usage"]["example"]
    md += "```\n\n"

    md += "**Notes:**\n"
    for note in docs["usage"]["notes"]:
        md += f"- {note}\n"
    md += "\n"

    # Modules
    md += "## Modules\n\n"
    for module_name, module_info in docs.get("modules", {}).items():
        md += f"### `{module_name}`\n\n"
        md += f"**Import:** `{module_info['import']}`\n\n"
        md += f"{module_info['description']}\n\n"

        if module_info.get("docstring"):
            md += f"{module_info['docstring']}\n\n"

        md += "**Methods:**\n\n"
        for method_name, method_info in module_info.get("methods", {}).items():
            sig = method_info.get("signature", "()")
            md += f"#### `{method_name}{sig}`\n\n"
            if method_info.get("docstring"):
                md += f"{method_info['docstring']}\n\n"

    # Constants
    if "constants" in docs:
        md += "## Constants\n\n"
        for const_name, const_info in docs["constants"].items():
            md += f"### {const_name}\n\n"
            if isinstance(const_info, dict):
                if "description" in const_info:
                    md += f"{const_info['description']}\n\n"
                for k, v in const_info.items():
                    if k != "description":
                        md += f"- `{k}`: {v}\n"
            md += "\n"

    # Advanced
    if "advanced" in docs:
        md += "## Advanced (Direct Backend Access)\n\n"
        for backend_name, backend_info in docs["advanced"].items():
            md += f"### `{backend_name}`\n\n"
            md += f"{backend_info['description']}\n\n"
            if "example" in backend_info:
                md += "```python\n"
                md += backend_info["example"]
                md += "```\n\n"
            if "methods" in backend_info:
                md += "**Methods:**\n"
                for method in backend_info["methods"]:
                    md += f"- `{method}`\n"
                md += "\n"

    return {"markdown": md}
