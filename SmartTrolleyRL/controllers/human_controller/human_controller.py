"""Controller for the one designated follow target; distractors use another controller."""
from controller import Supervisor
import math
robot = Supervisor()
node = robot.getFromDef("TARGET_HUMAN")
field = node.getField("translation") if node else None
dt = int(robot.getBasicTimeStep()); t = 0.0
while robot.step(dt) != -1:
    t += dt / 1000.0
    if field:
        field.setSFVec3f([1.4*math.sin(0.22*t), 0, 2.5+0.6*math.sin(0.13*t)])
