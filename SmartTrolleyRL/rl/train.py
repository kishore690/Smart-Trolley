"""Train a compact CPU PPO agent. Run from the project root: python -m rl.train"""
import argparse
import csv
from pathlib import Path
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList, CheckpointCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.utils import set_random_seed
from .config import EnvConfig
from .environment import SmartTrolleyEnv


class EpisodeMetricsCallback(BaseCallback):
    """Write collision and distance metrics alongside SB3's TensorBoard reward."""
    def __init__(self, output_path):
        super().__init__()
        self.output_path = Path(output_path)
        self.distance_sum = 0.0
        self.steps = 0
        self.collisions = 0

    def _on_training_start(self):
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.output_path.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=["episode", "timesteps", "mean_distance_error_m", "collisions"])
        self.writer.writeheader()
        self.episode = 0

    def _on_step(self):
        infos = self.locals.get("infos", [])
        dones = self.locals.get("dones", [])
        for index, info in enumerate(infos):
            self.distance_sum += float(info.get("distance_error", 0.0))
            self.steps += 1
            self.collisions += int(bool(info.get("collision", False)))
            if index < len(dones) and dones[index]:
                self.episode += 1
                self.writer.writerow({"episode": self.episode, "timesteps": self.num_timesteps,
                                      "mean_distance_error_m": self.distance_sum/max(1, self.steps),
                                      "collisions": self.collisions})
                self.file.flush()
                self.distance_sum = 0.0; self.steps = 0; self.collisions = 0
        return True

    def _on_training_end(self):
        if hasattr(self, "file"):
            self.file.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=500_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--run-name", default="ppo_trolley")
    parser.add_argument("--difficulty", choices=("easy", "medium", "hard"), default="medium")
    parser.add_argument("--checkpoint-freq", type=int, default=25_000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run_dir = root / "logs" / args.run_name
    checkpoint_dir = root / "models" / "checkpoints"
    run_dir.mkdir(parents=True, exist_ok=True); checkpoint_dir.mkdir(parents=True, exist_ok=True)
    set_random_seed(args.seed)
    torch.set_num_threads(1)
    env = Monitor(SmartTrolleyEnv(config=EnvConfig(difficulty=args.difficulty), seed=args.seed),
                  str(run_dir/"monitor.csv"))
    callbacks = CallbackList([
        CheckpointCallback(save_freq=max(1,args.checkpoint_freq), save_path=str(checkpoint_dir), name_prefix="ppo_trolley"),
        EpisodeMetricsCallback(run_dir/"episode_metrics.csv"),
    ])
    model = PPO("MlpPolicy", env, verbose=1, seed=args.seed, device=args.device,
                tensorboard_log=str(root/"logs"), n_steps=1024, batch_size=64,
                learning_rate=3e-4, gamma=0.99, gae_lambda=0.95, ent_coef=0.005,
                policy_kwargs={"net_arch": [64, 64]})
    model.learn(total_timesteps=args.timesteps, callback=callbacks,
                tb_log_name=args.run_name, progress_bar=False)
    model.save(str(root/"models"/"ppo_trolley"))
    env.close()
    print(f"Saved model to {root/'models'/'ppo_trolley.zip'}")
    print(f"Episode metrics: {run_dir/'episode_metrics.csv'}")


if __name__ == "__main__": main()
