"""Configurable reward shaping for human following and safe navigation."""
from __future__ import annotations
import math
import numpy as np
from .config import RewardConfig


def reward_terms(distance: float, angle: float, previous_action, action,
                 obstacle_distances, collision=False, human_visible=True,
                 previous_distance=None, config: RewardConfig | None = None):
    cfg = config or RewardConfig()
    if collision:
        return {"collision": -cfg.collision_penalty}
    a = np.asarray(action, dtype=float)
    prev = np.asarray(previous_action, dtype=float)
    clearance = min(obstacle_distances, default=cfg.obstacle_danger_distance + 1.0)
    terms = {
        "following_distance": cfg.distance_weight * math.exp(-((distance-cfg.desired_distance)/cfg.distance_sigma)**2),
        "alignment": cfg.alignment_weight * math.exp(-(angle/0.75)**2),
        "turning": -cfg.turning_weight * float(a[1]**2),
        "smoothness": -cfg.smoothness_weight * float(np.sum((a-prev)**2)),
        "clearance": cfg.obstacle_clearance_weight * min(1.0, max(0.0, clearance/cfg.obstacle_danger_distance-0.25)),
        "unsafe_proximity": -cfg.close_penalty * max(0.0, cfg.close_distance-distance)**2,
        "lost_target": -cfg.lost_target_penalty if not human_visible else 0.0,
    }
    if previous_distance is not None:
        # Progress is rewarded only when it reduces distance error, so it does
        # not encourage the trolley to keep closing past the desired spacing.
        before_error = abs(previous_distance-cfg.desired_distance)
        after_error = abs(distance-cfg.desired_distance)
        terms["approach_progress"] = cfg.progress_weight * float(np.clip(before_error-after_error, -0.15, 0.15))
    if prev[1] * a[1] < -0.05 and abs(prev[1]) > 0.2 and abs(a[1]) > 0.2:
        terms["turn_oscillation"] = -cfg.oscillation_penalty
    else:
        terms["turn_oscillation"] = 0.0
    if distance > cfg.desired_distance + 0.45 and clearance > cfg.obstacle_danger_distance and a[0] < -0.75:
        terms["unnecessary_stop"] = -cfg.unnecessary_stop_penalty
    else:
        terms["unnecessary_stop"] = 0.0
    return terms


def calculate_reward(distance, angle, previous_action, action, obstacle_distances,
                     collision=False, human_visible=True, target_distance=1.0,
                     previous_distance=None, config: RewardConfig | None = None):
    cfg = config or RewardConfig(desired_distance=target_distance)
    return float(sum(reward_terms(distance, angle, previous_action, action,
                                  obstacle_distances, collision, human_visible,
                                  previous_distance, cfg).values()))
