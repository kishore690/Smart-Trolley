"""Moves non-target pedestrians; trolley intentionally never selects these DEFs."""
from controller import Supervisor
import math

robot = Supervisor()
node = robot.getSelf()
translation = node.getField("translation")
base_x, _, base_z = translation.getSFVec3f()
name = node.getField("name").getSFString()
phase = 0.0 if name.endswith("a") else math.pi
dt = int(robot.getBasicTimeStep())
t = 0.0
while robot.step(dt) != -1:
    t += dt / 1000.0
    x = base_x + 0.38 * math.sin(0.30*t + phase)
    z = base_z + 0.62 * math.sin(0.21*t + phase)
    translation.setSFVec3f([x, 0.0, z])
