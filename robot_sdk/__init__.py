"""Robot SDK for submitted code execution.

This package provides a simplified API for external agents to control the robot.
Code submitted via /code/execute runs in a subprocess with access to these modules.

Example usage:
    from robot_sdk import arm, base, gripper
    import time

    # Move arm to position
    arm.move_joints([0.0, -0.5, 0.0, -2.0, 0.0, 1.5, 0.7])
    time.sleep(1)

    # Open gripper
    gripper.open()

    # Move base forward
    base.move_delta(dx=0.5, frame="local")
"""

from robot_sdk.arm import ArmAPI
from robot_sdk.base import BaseAPI
from robot_sdk.gripper import GripperAPI
from robot_sdk.sensors import SensorAPI

# Global instances (initialized by CodeExecutor before running submitted code)
arm: ArmAPI = None  # type: ignore
base: BaseAPI = None  # type: ignore
gripper: GripperAPI = None  # type: ignore
sensors: SensorAPI = None  # type: ignore

__all__ = ["arm", "base", "gripper", "sensors", "ArmAPI", "BaseAPI", "GripperAPI", "SensorAPI"]
