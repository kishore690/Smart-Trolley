"""Stable Webots Supervisor demo follower with range-sensor obstacle overrides."""
from controller import Supervisor
import math
from pathlib import Path

robot = Supervisor()
dt_ms = int(robot.getBasicTimeStep())
dt = dt_ms / 1000.0
left = robot.getDevice("left wheel motor")
right = robot.getDevice("right wheel motor")
left.setPosition(float("inf")); right.setPosition(float("inf"))
left.setVelocity(0); right.setVelocity(0)
sensors = [robot.getDevice(n) for n in ("front distance", "left distance", "right distance")]
for sensor in sensors: sensor.enable(dt_ms)
human = robot.getFromDef("TARGET_HUMAN")
if human is None: raise RuntimeError("World is missing DEF TARGET_HUMAN")
human_translation = human.getField("translation")
self_node = robot.getSelf()
position_field = self_node.getField("translation")
rotation_field = self_node.getField("rotation")
position = position_field.getSFVec3f()
x, _, z = position
yaw = 0.0
wheel_radius, axle, desired_distance = 0.16, 0.74, 1.0
max_linear_speed, max_angular_speed, max_sensor_range = 1.0, 1.5, 8.0
current_linear_velocity = 0.0
current_angular_velocity = 0.0
steps = 0
last_action = [0.0, 0.0]
policy = None
model_path = Path(__file__).resolve().parents[2] / "models" / "ppo_trolley.zip"
if model_path.is_file():
    try:
        from stable_baselines3 import PPO
        policy = PPO.load(str(model_path), device="cpu")
        print(f"loaded PPO policy: {model_path}")
    except Exception as exc:
        print(f"PPO policy could not load ({exc}); using feedback baseline")

while robot.step(dt_ms) != -1:
    steps += 1
    hx, _, hz = human_translation.getSFVec3f()
    dx, dz = hx - x, hz - z
    distance = math.hypot(dx, dz)
    desired_yaw = math.atan2(-dx, -dz)  # Webots forward is local -Z.
    bearing = (desired_yaw - yaw + math.pi) % (2 * math.pi) - math.pi
    front, left_range, right_range = [s.getValue() / 1000.0 for s in sensors]

    target_visible = distance <= max_sensor_range
    front, left_range, right_range = [max(0.0, min(max_sensor_range, value)) for value in (front,left_range,right_range)]
    # PPO and Gym share the same normalized ten-value observation order. A baseline
    # follower is used until a trained model has been saved in models/.
    if policy is not None:
        import numpy as np
        observation = np.asarray([min(distance, 8.0),
                                  max(-3.0, min(3.0, distance * math.sin(bearing)))/3.0,
                                  bearing/math.pi,
                                  front/8.0, left_range/8.0, right_range/8.0,
                                  current_linear_velocity/max_linear_speed,
                                  current_angular_velocity/max_angular_speed,
                                  last_action[0], last_action[1]], dtype=np.float32)
        observation[0] /= 8.0
        action, _ = policy.predict(observation, deterministic=True)
        last_action = [float(action[0]), float(action[1])]
        linear = (last_action[0] + 1.0) * 0.5 * max_linear_speed
        angular = last_action[1] * max_angular_speed
    else:
        angular = max(-1.4, min(1.4, 2.0 * bearing))
        linear = max(0.0, min(0.55, 0.8 * (distance - desired_distance)))
        linear *= max(0.0, math.cos(bearing))
    if distance < 0.62:
        linear = 0.0
    if not target_visible:
        linear = 0.0
        angular = 0.0
    if front < 0.75:
        linear = min(linear, 0.08)
        angular = 0.8 if left_range > right_range else -0.8
    if left_range < 0.38 and right_range < 0.38:
        linear = 0.0
        angular = 0.0
    elif left_range < 0.38:
        linear = min(linear, 0.08)
        angular = -0.8
    elif right_range < 0.38:
        linear = min(linear, 0.08)
        angular = 0.8

    # This is a kinematic Supervisor demo: moving the root directly avoids
    # toppling in this minimal two-wheel model, while the wheel motors and
    # range sensors remain active Webots devices for visualization/control.
    yaw = (yaw + angular * dt + math.pi) % (2 * math.pi) - math.pi
    x += -math.sin(yaw) * linear * dt
    z += -math.cos(yaw) * linear * dt
    position_field.setSFVec3f([x, 0.25, z])
    rotation_field.setSFRotation([0, 1, 0, yaw])
    vl = (linear - angular * axle / 2) / wheel_radius
    vr = (linear + angular * axle / 2) / wheel_radius
    left.setVelocity(max(-6.0, min(6.0, vl)))
    right.setVelocity(max(-6.0, min(6.0, vr)))
    current_linear_velocity = linear
    current_angular_velocity = angular
    last_action = [max(-1.0,min(1.0,2.0*linear/max_linear_speed-1.0)),
                   max(-1.0,min(1.0,angular/max_angular_speed))]
    if steps == 160:
        print(f"trolley controller active; pose=({x:.2f}, {z:.2f}) "
              f"human_distance={distance:.2f}m wheel_speeds=({vl:.2f}, {vr:.2f})")
