"""Seeded Gymnasium differential-drive plant for fast CPU PPO training.

Webots controllers use the same normalized ten-element observation and action
contract. This plant supplies ray-cast virtual range sensors, randomized target
trajectories, and collision geometry without requiring Webots per training step.
"""
from __future__ import annotations
import math
import gymnasium as gym
import numpy as np
from gymnasium import spaces
from .config import EnvConfig, RewardConfig, get_difficulty
from .rewards import reward_terms


class SmartTrolleyEnv(gym.Env):
    metadata = {"render_modes": ["human"], "render_fps": 10}

    def __init__(self, render_mode=None, max_episode_steps=None, seed=None,
                 difficulty="medium", config: EnvConfig | None = None,
                 reward_config: RewardConfig | None = None):
        super().__init__()
        self.config = config or EnvConfig(difficulty=difficulty,
                                         max_episode_steps=max_episode_steps or 600)
        if max_episode_steps is not None and config is not None:
            self.config = EnvConfig(**{**config.__dict__, "max_episode_steps": int(max_episode_steps)})
        self.difficulty = get_difficulty(self.config.difficulty)
        self.reward_config = reward_config or RewardConfig(desired_distance=self.config.target_distance)
        self.render_mode = render_mode
        self.dt = self.config.dt
        self.target_distance = self.config.target_distance
        self.max_speed = self.config.max_speed
        self.max_angular = self.config.max_angular_speed
        self.max_range = self.config.max_sensor_range
        self.max_episode_steps = int(self.config.max_episode_steps)
        self.action_space = spaces.Box(-1.0, 1.0, shape=(2,), dtype=np.float32)
        # [distance, lateral, bearing, front/left/right ranges, v, omega, prev v, prev omega]
        self.observation_space = spaces.Box(
            low=np.array([0, -1, -1, 0, 0, 0, 0, -1, -1, -1], dtype=np.float32),
            high=np.ones(10, dtype=np.float32), dtype=np.float32)
        self.reset(seed=seed)

    @staticmethod
    def _wrap(angle):
        return (angle + math.pi) % (2 * math.pi) - math.pi

    def _bearing(self):
        delta = self.human - self.robot
        return float(np.linalg.norm(delta)), self._wrap(math.atan2(delta[1], delta[0]) - self.heading)

    def _human_visible(self):
        distance, _ = self._bearing()
        if distance > self.max_range:
            return False
        ray = self.human - self.robot
        ray_len2 = float(ray @ ray)
        for ox, oy, radius in self.obstacles:
            center = np.array([ox, oy]) - self.robot
            t = float(np.clip((center @ ray) / max(ray_len2, 1e-9), 0.0, 1.0))
            if np.linalg.norm(center-t*ray) < radius + 0.12 and t < 0.98:
                return False
        return True

    def _ray_circle(self, origin, direction, center, radius):
        rel = np.asarray(center) - origin
        projection = float(rel @ direction)
        perpendicular_sq = float(rel @ rel) - projection*projection
        if projection <= 0 or perpendicular_sq >= radius*radius:
            return self.max_range
        return max(0.0, projection-math.sqrt(radius*radius-perpendicular_sq))

    def _sensor_values(self):
        values = []
        half_w, half_h = self.config.half_width, self.config.half_height
        for offset in (0.0, 0.72, -0.72):
            ray_angle = self.heading + offset
            direction = np.array([math.cos(ray_angle), math.sin(ray_angle)])
            origin = self.robot + direction*self.config.robot_radius*0.7
            hits = []
            for axis, bound in ((0, half_w), (0, -half_w), (1, half_h), (1, -half_h)):
                component = direction[axis]
                if abs(component) < 1e-8:
                    continue
                t = (bound-origin[axis])/component
                other_axis = 1-axis
                other = origin[other_axis] + t*direction[other_axis]
                other_bound = half_h if axis == 0 else half_w
                if t > 0 and abs(other) <= other_bound:
                    hits.append(t-self.config.robot_radius)
            for ox, oy, radius in self.obstacles:
                hits.append(self._ray_circle(origin, direction, (ox, oy), radius+self.config.robot_radius))
            distance = min(hits, default=self.max_range)
            noise = self.np_random.normal(0.0, self.difficulty.sensor_noise) if self.difficulty.sensor_noise else 0.0
            values.append(float(np.clip(distance+noise, 0.0, self.max_range)))
        return values

    def _observation(self):
        distance, angle = self._bearing()
        lateral = distance*math.sin(angle)
        front, left_range, right_range = self._sensor_values()
        # All continuous inputs are scaled to [-1, 1] or [0, 1].
        return np.asarray([
            np.clip(distance/self.max_range, 0, 1),
            np.clip(lateral/3.0, -1, 1),
            np.clip(angle/math.pi, -1, 1),
            np.clip(front/self.max_range, 0, 1),
            np.clip(left_range/self.max_range, 0, 1),
            np.clip(right_range/self.max_range, 0, 1),
            np.clip(self.linear_velocity/self.max_speed, 0, 1),
            np.clip(self.angular_velocity/self.max_angular, -1, 1),
            self.last_action[0], self.last_action[1],
        ], dtype=np.float32)

    def _spawn_obstacles(self):
        count = int(self.np_random.integers(self.difficulty.obstacle_count[0], self.difficulty.obstacle_count[1]+1))
        obstacles = []
        for _ in range(count):
            for _attempt in range(50):
                x = float(self.np_random.uniform(-6.5, 6.5))
                y = float(self.np_random.uniform(-4.5, 4.5))
                radius = float(self.np_random.uniform(0.22, 0.43))
                if np.linalg.norm([x, y]) > 1.1 and np.linalg.norm(np.array([x,y])-self.human) > 0.8 and all(np.linalg.norm(np.array([x,y])-o[:2]) > radius+o[2]+0.2 for o in obstacles):
                    obstacles.append((x, y, radius)); break
        return obstacles

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.robot = np.array([0.0, 0.0], dtype=float)
        self.heading = float(self.np_random.uniform(-0.12, 0.12))
        distance = float(self.np_random.uniform(2.0, 3.4))
        bearing = float(self.np_random.uniform(-0.65, 0.65))
        self.human = self.robot + distance*np.array([math.cos(self.heading+bearing), math.sin(self.heading+bearing)])
        self.human_base_heading = float(self.np_random.uniform(-0.45, 0.45))
        self.human_heading = self.human_base_heading
        self.human_speed = float(self.np_random.uniform(*self.difficulty.human_speed))
        self.trajectory = str(self.np_random.choice(["straight", "sine", "zigzag", "wander"]))
        self.trajectory_time = 0.0
        self.wander_turn = 0.0
        self.obstacles = self._spawn_obstacles()
        self.linear_velocity = 0.0
        self.angular_velocity = 0.0
        self.last_action = np.zeros(2, dtype=np.float32)
        self.steps = 0
        self.previous_distance = float(np.linalg.norm(self.human-self.robot))
        return self._observation(), {"collision": False, "trajectory": self.trajectory, "difficulty": self.config.difficulty}

    def _move_human(self):
        self.trajectory_time += self.dt
        if self.trajectory == "sine":
            self.human_heading = self.human_base_heading + 0.42*math.sin(0.72*self.trajectory_time)
        elif self.trajectory == "zigzag":
            self.human_heading = self.human_base_heading + (0.55 if int(self.trajectory_time/2.5)%2 == 0 else -0.55)
        elif self.trajectory == "wander":
            self.wander_turn = float(np.clip(self.wander_turn+self.np_random.normal(0, self.difficulty.turn_rate), -1.0, 1.0))
            self.human_heading = self.human_base_heading+self.wander_turn
        self.human += np.array([math.cos(self.human_heading), math.sin(self.human_heading)])*self.human_speed*self.dt
        if abs(self.human[0]) > self.config.half_width-0.6:
            self.human_heading = math.pi-self.human_heading
            self.human_base_heading = math.pi-self.human_base_heading
        if abs(self.human[1]) > self.config.half_height-0.6:
            self.human_heading *= -1
            self.human_base_heading *= -1
        self.human[0] = np.clip(self.human[0], -self.config.half_width+0.6, self.config.half_width-0.6)
        self.human[1] = np.clip(self.human[1], -self.config.half_height+0.6, self.config.half_height-0.6)

    def _collision(self, distance):
        bounds_hit = (abs(self.robot[0]) >= self.config.half_width-self.config.robot_radius or
                      abs(self.robot[1]) >= self.config.half_height-self.config.robot_radius)
        obstacle_hit = any(np.linalg.norm(self.robot-np.array([ox,oy])) <= radius+self.config.robot_radius
                           for ox,oy,radius in self.obstacles)
        return bool(bounds_hit or obstacle_hit or distance <= 0.42)

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=np.float32).reshape(2), -1.0, 1.0)
        distance_before, _ = self._bearing()
        linear = float((action[0]+1.0)*0.5*self.max_speed)
        angular = float(action[1]*self.max_angular)
        self.angular_velocity = angular
        self.linear_velocity = linear
        self.heading = self._wrap(self.heading+angular*self.dt)
        self.robot += np.array([math.cos(self.heading), math.sin(self.heading)])*linear*self.dt
        self._move_human()
        distance, angle = self._bearing()
        sensors = self._sensor_values()
        collision = self._collision(distance)
        visible = self._human_visible()
        terms = reward_terms(distance, angle, self.last_action, action, sensors,
                             collision, visible, self.previous_distance, self.reward_config)
        reward = float(sum(terms.values()))
        distance_error = abs(distance-self.target_distance)
        self.previous_distance = distance
        self.last_action = action.copy()
        self.steps += 1
        terminated = collision
        truncated = self.steps >= self.max_episode_steps
        info = {"collision": collision, "human_visible": visible, "distance": distance,
                "distance_error": distance_error, "linear_velocity": linear,
                "angular_velocity": angular, "trajectory": self.trajectory,
                "reward_terms": terms, "obstacle_distances": sensors}
        return self._observation(), reward, terminated, truncated, info

    def render(self):
        if self.render_mode == "human":
            print(f"robot={self.robot.round(2)} human={self.human.round(2)} "
                  f"distance={self._bearing()[0]:.2f}m trajectory={self.trajectory}")

    def close(self):
        pass
