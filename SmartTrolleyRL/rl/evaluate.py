"""Evaluate policy reward, distance error, collisions, and optionally open Webots."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import numpy as np
from stable_baselines3 import PPO
from .config import EnvConfig
from .environment import SmartTrolleyEnv


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--model", default=None); parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--seed", type=int, default=101); parser.add_argument("--render", action="store_true")
    parser.add_argument("--difficulty", choices=("easy", "medium", "hard"), default="medium")
    parser.add_argument("--webots", action="store_true", help="launch the rendered Webots world after evaluation")
    parser.add_argument("--webots-bin", default=None)
    args=parser.parse_args(); root=Path(__file__).resolve().parents[1]
    model_path=args.model or str(root/"models"/"ppo_trolley")
    model=PPO.load(model_path, device="cpu")
    env=SmartTrolleyEnv(render_mode="human" if args.render else None,
                        config=EnvConfig(difficulty=args.difficulty))
    episode_rewards=[]; episode_errors=[]; total_collisions=0; all_errors=[]
    for episode in range(args.episodes):
        obs,_=env.reset(seed=args.seed+episode); reward_sum=0.0; errors=[]; collisions=0
        while True:
            action,_=model.predict(obs, deterministic=True)
            obs,reward,terminated,truncated,info=env.step(action)
            reward_sum+=reward; errors.append(info["distance_error"])
            collisions+=int(info["collision"])
            if args.render: env.render()
            if terminated or truncated: break
        episode_rewards.append(reward_sum); episode_errors.append(float(np.mean(errors)))
        all_errors.extend(errors); total_collisions+=collisions
        print(f"episode {episode+1}: reward={reward_sum:.1f}, mean_distance_error={episode_errors[-1]:.3f}m, collisions={collisions}, trajectory={info['trajectory']}")
    print(f"mean reward={np.mean(episode_rewards):.2f}; mean distance error={np.mean(episode_errors):.3f}m; total collisions={total_collisions}; samples={len(all_errors)}")
    env.close()
    if args.webots:
        candidates=[args.webots_bin, shutil.which("webots"),
                    os.path.join(os.environ.get("WEBOTS_HOME", ""),"msys64","mingw64","bin","webots.exe"),
                    r"C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"]
        executable=next((path for path in candidates if path and Path(path).is_file()),None)
        if executable is None: raise SystemExit("Webots not found; pass --webots-bin or set WEBOTS_HOME")
        subprocess.Popen([executable,str(root/"worlds"/"smart_trolley_rl.wbt")],cwd=str(root))


if __name__ == "__main__": main()
