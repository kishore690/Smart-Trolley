"""Shared, serializable defaults for training, rewards, and virtual scenarios."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RewardConfig:
    desired_distance: float = 1.0
    distance_sigma: float = 0.55
    distance_weight: float = 1.5
    alignment_weight: float = 0.35
    progress_weight: float = 0.8
    smoothness_weight: float = 0.12
    turning_weight: float = 0.06
    oscillation_penalty: float = 0.18
    obstacle_clearance_weight: float = 0.30
    obstacle_danger_distance: float = 0.80
    close_distance: float = 0.60
    close_penalty: float = 3.0
    lost_target_penalty: float = 2.0
    collision_penalty: float = 100.0
    unnecessary_stop_penalty: float = 0.12


@dataclass(frozen=True)
class DifficultyConfig:
    obstacle_count: tuple[int, int]
    human_speed: tuple[float, float]
    turn_rate: float
    sensor_noise: float


DIFFICULTIES = {
    "easy": DifficultyConfig((2, 4), (0.12, 0.30), 0.08, 0.0),
    "medium": DifficultyConfig((3, 7), (0.16, 0.48), 0.16, 0.015),
    "hard": DifficultyConfig((6, 10), (0.22, 0.62), 0.28, 0.035),
}


@dataclass(frozen=True)
class EnvConfig:
    difficulty: str = "medium"
    dt: float = 0.1
    max_episode_steps: int = 600
    target_distance: float = 1.0
    max_speed: float = 1.0
    max_angular_speed: float = 1.5
    max_sensor_range: float = 8.0
    half_width: float = 8.0
    half_height: float = 6.0
    robot_radius: float = 0.25


def get_difficulty(name: str) -> DifficultyConfig:
    try:
        return DIFFICULTIES[name.lower()]
    except KeyError as exc:
        raise ValueError(f"difficulty must be one of {', '.join(DIFFICULTIES)}") from exc
