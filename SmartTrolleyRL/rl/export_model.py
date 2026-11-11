"""Export PPO policy to ONNX for compact Raspberry Pi CPU inference."""
import argparse
from pathlib import Path
import torch
from stable_baselines3 import PPO


class DeterministicActor(torch.nn.Module):
    def __init__(self, policy):
        super().__init__()
        self.policy = policy

    def forward(self, observation):
        return torch.clamp(self.policy._predict(observation, deterministic=True), -1.0, 1.0)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--model", default=None); p.add_argument("--output", default=None); a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    model=PPO.load(a.model or str(root/"models"/"ppo_trolley"), device="cpu")
    out=Path(a.output) if a.output else root/"models"/"ppo_trolley.onnx"
    out.parent.mkdir(parents=True, exist_ok=True)
    obs=torch.zeros((1,10),dtype=torch.float32)
    actor = DeterministicActor(model.policy).eval()
    torch.onnx.export(actor, obs, out, input_names=["observation"], output_names=["action"],
                      dynamic_axes={"observation":{0:"batch"},"action":{0:"batch"}},
                      opset_version=17, dynamo=False)
    print(f"Exported {out}")


if __name__ == "__main__": main()
