"""Fail-closed command limiter. PPO output never reaches the motor driver directly."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SafetyLimits:
    policy_max_speed_m_s: float = 1.0
    max_speed_m_s: float = 0.25
    max_turn_rate_rad_s: float = 0.65
    min_human_distance_m: float = 0.70
    obstacle_stop_m: float = 0.55
    obstacle_slow_m: float = 1.0
    unknown_obstacle_speed_m_s: float = 0.08


class SafetyController:
    def __init__(self, limits=None):
        self.limits = limits or SafetyLimits()

    def limit(self, policy_action, *, target_visible, target_distance_m,
              obstacle_distances_m, inference_ok=True, emergency_stop=False):
        """Return (linear m/s, angular rad/s, reason); stop on any failed prerequisite."""
        if emergency_stop:
            return 0.0, 0.0, "emergency_stop"
        if not inference_ok:
            return 0.0, 0.0, "inference_failure"
        if not target_visible or target_distance_m is None:
            return 0.0, 0.0, "human_lost"
        if not math.isfinite(target_distance_m):
            return 0.0, 0.0, "invalid_target_range"
        action = [float(policy_action[0]), float(policy_action[1])]
        if not all(math.isfinite(v) for v in action):
            return 0.0, 0.0, "invalid_policy_action"
        lim = self.limits
        speed = (max(-1.0, min(1.0, action[0]))+1.0)*0.5*lim.policy_max_speed_m_s
        turn = max(-1.0, min(1.0, action[1]))*1.5
        speed = min(speed, lim.max_speed_m_s)
        turn = max(-lim.max_turn_rate_rad_s, min(lim.max_turn_rate_rad_s, turn))
        if target_distance_m < lim.min_human_distance_m:
            return 0.0, 0.0, "human_too_close"

        front, left, right = obstacle_distances_m
        if front is None:
            speed = min(speed, lim.unknown_obstacle_speed_m_s)
            # No metric range: allow only a slow crawl and a very small turn.
            turn = max(-0.20,min(0.20,turn))
        elif left is None or right is None:
            turn = max(-0.20,min(0.20,turn))
        elif front < lim.obstacle_stop_m:
            speed = 0.0
            if left is None or right is None or max(left, right) < lim.obstacle_slow_m:
                turn = 0.0
            else:
                turn = lim.max_turn_rate_rad_s if left > right else -lim.max_turn_rate_rad_s
        elif front < lim.obstacle_slow_m:
            speed = min(speed, lim.unknown_obstacle_speed_m_s)
        return speed, turn, "limited" if speed < lim.policy_max_speed_m_s or abs(turn) < 1.5 else "policy"
