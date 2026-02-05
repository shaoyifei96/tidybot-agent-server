"""Example: Pick and place skill using robot_sdk.

This is an example of code that would be submitted via POST /code/execute.
"""

from robot_sdk import arm, base, gripper, sensors
import time

print("Starting pick and place skill...")

# Step 1: Activate gripper
print("Activating gripper...")
gripper.activate()

# Step 2: Open gripper
print("Opening gripper...")
gripper.open()
time.sleep(0.5)

# Step 3: Move arm to pre-grasp position
print("Moving arm to pre-grasp position...")
arm.move_to_pose(x=0.5, y=0.0, z=0.3)
time.sleep(0.5)

# Step 4: Get current end-effector position
ee_pos = sensors.get_ee_position()
print(f"Current EE position: x={ee_pos[0]:.3f}, y={ee_pos[1]:.3f}, z={ee_pos[2]:.3f}")

# Step 5: Move down to grasp
print("Moving down to grasp...")
arm.move_delta(dz=-0.1, frame="ee")
time.sleep(0.5)

# Step 6: Grasp object
print("Grasping object...")
grasped = gripper.grasp(force=100)
if grasped:
    print("Object grasped successfully!")
else:
    print("Warning: No object detected")
time.sleep(0.5)

# Step 7: Lift object
print("Lifting object...")
arm.move_delta(dz=0.2, frame="ee")
time.sleep(0.5)

# Step 8: Move base to dropoff location
print("Moving base to dropoff location...")
base.move_delta(dx=0.5, frame="local")
time.sleep(0.5)

# Step 9: Lower object
print("Lowering object...")
arm.move_delta(dz=-0.15, frame="ee")
time.sleep(0.5)

# Step 10: Release object
print("Releasing object...")
gripper.open()
time.sleep(0.5)

# Step 11: Lift arm
print("Lifting arm...")
arm.move_delta(dz=0.1, frame="ee")

print("Pick and place skill completed!")
